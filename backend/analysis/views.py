import json

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .examples import EXAMPLES
from .engine import InputError, Params, ParseError, analyze
from . import llm
from .serializers import (AnalyzeSerializer, DescribeSerializer, LearnedTuningSerializer, SimulateSerializer,
                          TuneSerializer, TutorSerializer)



@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def examples(request):
    return Response(EXAMPLES)


@api_view(["POST"])
def analyze_view(request):
    ser = AnalyzeSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    spec, params = split_request(ser.validated_data)
    try:
        result = analyze(spec, params)
    except (ParseError, InputError, ValueError) as exc:
        return Response({"errors": {"system": [str(exc)]}}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


def split_request(data: dict) -> tuple[dict, Params]:
    data = dict(data)
    spec = {k: data.pop(k) for k in AnalyzeSerializer.LOOP_FIELDS if k in data}
    return spec, Params(**data)


def feature_unavailable(feature: str) -> Response | None:
    """503 com instruções quando o recurso de IA está desabilitado ou o Ollama não responde."""
    if not llm.enabled(feature):
        return Response({"errors": {"llm": [llm.disabled_message(feature)]}}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if llm.provider(feature) == "ollama" and not llm.ollama.reachable():
        return Response({"errors": {"llm": [llm.ollama.unreachable_message()]}}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return None


@api_view(["GET"])
def llm_status(request):
    return Response(llm.status())


@api_view(["POST"])
def describe_view(request):
    ser = DescribeSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    try:
        result = llm.describe(ser.validated_data["text"])
    except llm.LLMUnavailable as exc:
        return Response({"errors": {"llm": [str(exc)]}}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except (InputError, ValueError) as exc:
        return Response({"errors": {"llm": [str(exc)]}}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as exc:  # noqa: BLE001 - erros da API viram mensagens amigáveis
        return Response({"errors": {"llm": [llm.friendly_error(exc)]}}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(["POST"])
def tutor_view(request):
    ser = TutorSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    unavailable = feature_unavailable("tutor")
    if unavailable:
        return unavailable
    spec, params = split_request(ser.validated_data["request"])
    messages = ser.validated_data["messages"]
    try:
        llm.cached_analysis(spec, params)  # valida a malha antes de abrir o stream
    except (ParseError, InputError, ValueError) as exc:
        return Response({"errors": {"system": [str(exc)]}}, status=status.HTTP_400_BAD_REQUEST)

    def events():
        try:
            for chunk in llm.tutor_stream(spec, params, messages):
                yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': llm.friendly_error(exc)}, ensure_ascii=False)}\n\n"

    resp = StreamingHttpResponse(events(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@api_view(["POST"])
def simulate_view(request):
    from .engine.loop import build_loop
    from .engine.report import sanitize
    from .engine.simulate import SimParams, simulate

    ser = SimulateSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    spec, _ = split_request(ser.validated_data["request"])
    try:
        lp = build_loop(spec)
        result = simulate(lp, SimParams(**ser.validated_data["sim"]))
    except (ParseError, InputError, ValueError) as exc:
        return Response({"errors": {"system": [str(exc)]}}, status=status.HTTP_400_BAD_REQUEST)
    return Response(sanitize(result))


@api_view(["POST"])
def tune_view(request):
    from . import tuning
    from .engine.report import sanitize
    from .engine.simulate import SimParams

    ser = TuneSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    unavailable = feature_unavailable("tuning")
    if unavailable:
        return unavailable
    spec, params = split_request(ser.validated_data["request"])
    base = SimParams(**ser.validated_data["sim"])
    try:
        llm.cached_analysis(spec, params)
    except (ParseError, InputError, ValueError) as exc:
        return Response({"errors": {"system": [str(exc)]}}, status=status.HTTP_400_BAD_REQUEST)

    def events():
        try:
            for ev in tuning.tune_stream(spec, params, base, ser.validated_data["goal"]):
                yield f"data: {json.dumps(sanitize(ev), ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'error': llm.friendly_error(exc)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    resp = StreamingHttpResponse(events(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@api_view(["POST"])
def learned_tuning_view(request):
    """Sintonia sugerida pela rede neural treinada com dados gerados pela própria ferramenta."""
    from .engine import learned
    from .engine.loop import build_loop
    from .engine.report import sanitize

    ser = LearnedTuningSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)
    spec, _ = split_request(ser.validated_data["request"])
    try:
        result = learned.suggest(build_loop(spec))
    except (ParseError, InputError, ValueError) as exc:
        return Response({"errors": {"system": [str(exc)]}}, status=status.HTTP_400_BAD_REQUEST)
    return Response(sanitize(result))
