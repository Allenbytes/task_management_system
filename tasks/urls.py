from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from .views import LogoutView, RegisterView, TaskViewSet, home_view

router = DefaultRouter()
router.register('tasks', TaskViewSet, basename='task')

urlpatterns = [
    path('', home_view, name='api_home'),
    path('register/', RegisterView.as_view(), name='api_register'),
    path('login/', obtain_auth_token, name='api_token_auth'),
    path('logout/', LogoutView.as_view(), name='api_logout'),
    path('', include(router.urls)),
]
