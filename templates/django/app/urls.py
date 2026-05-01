from django.urls import path

from .views import health_view, items_view

urlpatterns = [
    path("health", health_view),
    path("items", items_view),
]
