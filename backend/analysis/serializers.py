from rest_framework import serializers

TEXT = {"required": False, "allow_blank": True, "max_length": 2000}


class PlantSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["tf", "zpk", "ss"], default="tf")
    num = serializers.CharField(**TEXT)
    den = serializers.CharField(**TEXT)
    zeros = serializers.CharField(**TEXT)
    poles = serializers.CharField(**TEXT)
    gain = serializers.FloatField(required=False, default=1.0)
    A = serializers.CharField(**TEXT)
    B = serializers.CharField(**TEXT)
    C = serializers.CharField(**TEXT)
    D = serializers.CharField(**TEXT)


class ControllerSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["tf", "pid"], default="tf")
    num = serializers.CharField(**TEXT)
    den = serializers.CharField(**TEXT)
    kp = serializers.FloatField(required=False, default=0.0)
    ki = serializers.FloatField(required=False, default=0.0)
    kd = serializers.FloatField(required=False, default=0.0)


class SensorSerializer(serializers.Serializer):
    num = serializers.CharField(**TEXT)
    den = serializers.CharField(**TEXT)


class AnalyzeSerializer(serializers.Serializer):
    plant = PlantSerializer(required=False)
    # compatibilidade: planta informada diretamente como num/den
    num = serializers.CharField(required=False, max_length=300)
    den = serializers.CharField(required=False, max_length=300)
    controller = ControllerSerializer(required=False)
    sensor = SensorSerializer(required=False)
    feedback = serializers.ChoiceField(choices=["negative", "positive"], default="negative")
    delay = serializers.FloatField(default=0.0, min_value=0.0, max_value=1000.0)
    pade_order = serializers.IntegerField(default=2, min_value=1, max_value=6)

    k = serializers.FloatField(default=10.0, min_value=1e-9, max_value=1e9)
    k_step = serializers.FloatField(required=False, allow_null=True, min_value=1e-9, max_value=1e9)
    k_ramp = serializers.FloatField(required=False, allow_null=True, min_value=1e-9, max_value=1e9)
    k_impulse = serializers.FloatField(required=False, allow_null=True, min_value=1e-9, max_value=1e9)
    ess_target = serializers.FloatField(default=0.05, min_value=1e-6, max_value=0.99)
    ts_spec = serializers.FloatField(default=3.0, min_value=1e-3, max_value=1e4)
    mp_spec = serializers.FloatField(default=7.5, min_value=0.01, max_value=99.0)
    sine_freq = serializers.FloatField(default=1.0, min_value=1e-3, max_value=1e3)
    sine_amp = serializers.FloatField(default=1.0, min_value=1e-6, max_value=1e6)
    tfinal = serializers.FloatField(required=False, allow_null=True, min_value=0.1, max_value=1000)
    zn_include_gain = serializers.BooleanField(default=True)

    LOOP_FIELDS = ("plant", "num", "den", "controller", "sensor", "feedback", "delay", "pade_order")

    def validate(self, attrs):
        if "plant" not in attrs:
            if not attrs.get("num") or not attrs.get("den"):
                raise serializers.ValidationError({"plant": ["Informe a planta G(s)."]})
            attrs["plant"] = {"mode": "tf", "num": attrs["num"], "den": attrs["den"]}
        attrs.pop("num", None)
        attrs.pop("den", None)
        return attrs
