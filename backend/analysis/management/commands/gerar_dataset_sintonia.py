from pathlib import Path

from django.core.management.base import BaseCommand

from analysis.ml.dataset import generate

DEFAULT = Path(__file__).resolve().parents[2] / "ml" / "data" / "sintonia.csv"


class Command(BaseCommand):
    help = "Gera plantas aleatórias, extrai as características e rotula os ganhos ótimos de PID."

    def add_arguments(self, parser):
        parser.add_argument("--n", type=int, default=1600)
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--seed", type=int, default=1)
        parser.add_argument("--start", type=int, default=0, help="índice inicial (para continuar uma geração)")
        parser.add_argument("--out", type=Path, default=DEFAULT)

    def handle(self, *args, **o):
        n = generate(o["n"], o["out"], o["workers"], o["seed"], o["start"], log=lambda m: self.stdout.write(m))
        self.stdout.write(self.style.SUCCESS(f"{n} plantas válidas gravadas em {o['out']}"))
