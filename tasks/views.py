from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Task
from .serializers import TaskSerializer, UserSerializer


def home_view(request):
    return JsonResponse({
        'message': 'Welcome to the Task Management API!',
        'available_routes': [
            'POST /api/v1/register/',
            'POST /api/v1/login/',
            'POST /api/v1/logout/',
            'GET|POST /api/v1/tasks/',
            'GET|PUT|PATCH|DELETE /api/v1/tasks/<id>/',
        ],
    })


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key}, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Deleting the token invalidates it; logging in again issues a new one.
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskViewSet(viewsets.ModelViewSet):
    """CRUD for the current user's tasks. Supports ?status= and ?search= filters."""
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Scoping to the current user means other users' tasks return 404,
        # so update/delete need no extra ownership check.
        queryset = Task.objects.filter(created_by=self.request.user).order_by('-created_at')

        task_status = self.request.query_params.get('status')
        if task_status:
            queryset = queryset.filter(status=task_status)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(title__icontains=search)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
