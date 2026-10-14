from rest_framework import serializers


class AnalyzeSerializer(serializers.Serializer):
    num = serializers.CharField(max_length=300)
    den = serializers.CharField(max_length=300)
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
