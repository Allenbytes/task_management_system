from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.decorators import action
from .models import Task
from .serializers import TaskSerializer, UserSerializer, TokenSerializer
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse

def home_view(request):
    return JsonResponse({
        'message': 'Welcome to the Task Management API!',
        'available_routes': [
            '/api/v1/register/',
            '/api/v1/login/'
        ]
    })
class RegisterView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # Create a token for the user
            token, created = Token.objects.get_or_create(user=user)
            return Response({'token': token.key}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Login View (Using DRF's built-in obtain_auth_token)
from rest_framework.authtoken.views import obtain_auth_token

# Task Management ViewSet (CRUD operations for tasks)
class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Optionally restrict the returned tasks to the current user,
        by filtering against a `status` query parameter in the URL.
        """
        queryset = Task.objects.all()
        status = self.request.query_params.get('status', None)
        search = self.request.query_params.get('search', None)

        if status:
            queryset = queryset.filter(status=status)

        if search:
            queryset = queryset.filter(title__icontains=search)

        user = self.request.user
        if user.is_authenticated:
            queryset = queryset.filter(created_by=user)

        return queryset

    def perform_create(self, serializer):
        """
        Override the default perform_create method to associate the task
        with the current authenticated user.
        """
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        """
        Override the update method to check if the user is authorized to update the task.
        """
        task = self.get_object()
        if task.created_by != request.user:
            return Response({"detail": "You do not have permission to edit this task."},
                            status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Override the destroy method to check if the user is authorized to delete the task.
        """
        task = self.get_object()
        if task.created_by != request.user:
            return Response({"detail": "You do not have permission to delete this task."},
                            status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)
