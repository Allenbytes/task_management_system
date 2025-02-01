from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('tasks.urls')),  # Ensure the tasks URLs are included
    path('', RedirectView.as_view(url='/api/v1/', permanent=False)),  # Redirect root to /api/v1
]
