from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .examples import EXAMPLES
from .engine import InputError, Params, ParseError, analyze
from .serializers import AnalyzeSerializer



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
    data = dict(ser.validated_data)
    spec = {k: data.pop(k) for k in AnalyzeSerializer.LOOP_FIELDS if k in data}
    try:
        result = analyze(spec, Params(**data))
    except (ParseError, InputError, ValueError) as exc:
        return Response({"errors": {"system": [str(exc)]}}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)
