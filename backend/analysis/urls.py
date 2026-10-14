from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("examples/", views.examples, name="examples"),
    path("analyze/", views.analyze_view, name="analyze"),
]
