from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .engine import InputError, Params, ParseError, analyze
from .serializers import AnalyzeSerializer

EXAMPLES = [
    {
        "name": "Trabalho de Controle II (2013)",
        "num": "1",
        "den": "1 11.3 14 10",
        "description": "Planta de 3ª ordem do trabalho original: a1 = 11,3; a2 = 14; a3 = 10.",
    },
    {"name": "2ª ordem subamortecido", "num": "4", "den": "s^2 + 2s + 4", "description": "ωn = 2, ζ = 0,5."},
    {"name": "Com integrador (tipo 1)", "num": "1", "den": "s(s+1)(s+5)", "description": "Erro nulo ao degrau."},
    {"name": "Com zero", "num": "2(s+3)", "den": "(s+1)^2(s+5)(s+10)", "description": "Planta de 4ª ordem com um zero."},
    {"name": "Fase não mínima", "num": "-s + 1", "den": "(s+1)^3", "description": "Zero no semiplano direito."},
    {"name": "Instável em malha aberta", "num": "1", "den": "(s-1)(s+2)", "description": "Polo em s = 1."},
]


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
    num, den = data.pop("num"), data.pop("den")
    try:
        result = analyze(num, den, Params(**data))
    except (ParseError, InputError, ValueError) as exc:
        return Response({"errors": {"system": [str(exc)]}}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)
