from pathlib import Path

from django.core.management.base import BaseCommand

from analysis.engine.learned import MODEL_PATH, load_model
from analysis.ml.train import train

DATA = Path(__file__).resolve().parents[2] / "ml" / "data" / "sintonia.csv"


class Command(BaseCommand):
    help = "Treina a rede de sintonia (características da planta → ganhos de PID) e exporta para JSON."

    def add_arguments(self, parser):
        parser.add_argument("--data", type=Path, default=DATA)
        parser.add_argument("--out", type=Path, default=MODEL_PATH)
        parser.add_argument("--hidden", type=int, nargs="+", default=[32, 32])
        parser.add_argument("--seed", type=int, default=0)

    def handle(self, *args, **o):
        meta = train(o["data"], o["out"], tuple(o["hidden"]), seed=o["seed"], log=lambda m: self.stdout.write(m))
        load_model.cache_clear()
        self.stdout.write(self.style.SUCCESS(f"Modelo {meta['arquitetura']} salvo em {o['out']}"))
