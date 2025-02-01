from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from .views import RegisterView, home_view  # Make sure you import home_view

urlpatterns = [
    path('login/', obtain_auth_token, name='api_token_auth'),
    path('register/', RegisterView.as_view(), name='api_register'),
    path('', home_view, name='api_home'),  # Add a view for /api/v1/ to handle the base URL
]
