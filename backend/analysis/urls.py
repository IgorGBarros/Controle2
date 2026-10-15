from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("examples/", views.examples, name="examples"),
    path("analyze/", views.analyze_view, name="analyze"),
    path("simulate/", views.simulate_view, name="simulate"),
    path("llm/status/", views.llm_status, name="llm-status"),
    path("describe/", views.describe_view, name="describe"),
    path("tutor/", views.tutor_view, name="tutor"),
]
