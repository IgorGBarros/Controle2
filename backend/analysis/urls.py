from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("examples/", views.examples, name="examples"),
    path("analyze/", views.analyze_view, name="analyze"),
    path("simulate/", views.simulate_view, name="simulate"),
    path("learned-tuning/", views.learned_tuning_view, name="learned-tuning"),
    path("llm/status/", views.llm_status, name="llm-status"),
    path("describe/", views.describe_view, name="describe"),
    path("assistant/", views.assistant_view, name="assistant"),
]
