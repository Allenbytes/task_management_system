from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('study.urls')),
    path('', RedirectView.as_view(url='/api/', permanent=False)),
]
