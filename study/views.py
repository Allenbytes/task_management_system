from datetime import datetime

from django.core import signing
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import integrations, models, serializers
from .planner import ScheduleError, build_study_plan, study_statistics


class HomeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'message': 'Welcome to the Study Helper API!',
            'auth': 'POST /api/register/ or /api/token/, then send "Authorization: Bearer <access>".',
        })


# --- Accounts --------------------------------------------------------------

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {'username': user.username, 'email': user.email,
             'refresh': str(refresh), 'access': str(refresh.access_token)},
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    def post(self, request):
        # Blacklisting the refresh token stops it issuing new access tokens.
        # Access tokens are short-lived and expire on their own.
        try:
            RefreshToken(request.data.get('refresh', '')).blacklist()
        except TokenError:
            return Response({'refresh': 'A valid refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- CRUD ------------------------------------------------------------------

class OwnedViewSet(viewsets.ModelViewSet):
    """
    CRUD limited to the logged-in user's own records. Other users' records are
    simply not in the queryset, so requesting them returns 404.
    """

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TaskViewSet(OwnedViewSet):
    serializer_class = serializers.TaskSerializer


class SubjectLessonViewSet(OwnedViewSet):
    serializer_class = serializers.SubjectLessonSerializer


class SubjectDiaryViewSet(OwnedViewSet):
    serializer_class = serializers.SubjectDiarySerializer


class StudyScheduleViewSet(OwnedViewSet):
    serializer_class = serializers.StudyScheduleSerializer


class StudyResourceViewSet(OwnedViewSet):
    serializer_class = serializers.StudyResourceSerializer


class StudyBreakViewSet(OwnedViewSet):
    serializer_class = serializers.StudyBreakSerializer


class StudyProgressViewSet(OwnedViewSet):
    serializer_class = serializers.StudyProgressSerializer


class StudyChallengeViewSet(OwnedViewSet):
    serializer_class = serializers.StudyChallengeSerializer


class QuizViewSet(OwnedViewSet):
    serializer_class = serializers.QuizSerializer


class StudyPromptViewSet(OwnedViewSet):
    serializer_class = serializers.StudyPromptSerializer


class StudyReflectionViewSet(OwnedViewSet):
    serializer_class = serializers.StudyReflectionSerializer


class CourseGradeViewSet(OwnedViewSet):
    serializer_class = serializers.CourseGradeSerializer


class NoteViewSet(OwnedViewSet):
    serializer_class = serializers.NoteSerializer


# --- Generated data --------------------------------------------------------

class StudyStatisticsView(APIView):
    def get(self, request):
        grades = models.CourseGrade.objects.filter(user=request.user).values_list('course_name', 'grade')
        sessions = (models.StudyProgress.objects.filter(user=request.user, completed=True)
                    .values_list('subject', 'study_hours'))
        return Response(study_statistics(grades, sessions))


class GenerateStudyScheduleView(APIView):
    def get(self, request, schedule_id, timer_id):
        schedule = get_object_or_404(models.StudySchedule, pk=schedule_id, user=request.user)
        timer = get_object_or_404(models.StudyBreak, pk=timer_id, user=request.user)
        try:
            plan = build_study_plan(schedule.subject_list(), schedule.study_hours,
                                    timer.study_duration, timer.break_duration)
        except ScheduleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'message': 'Detailed study schedule generated successfully.',
            'study_date': schedule.study_date,
            'schedule': plan,
        })


# --- Third-party APIs ------------------------------------------------------

class MotivationView(APIView):
    def get(self, request):
        return Response(integrations.get_random_quote())


class TriviaQuizView(APIView):
    def get(self, request):
        subject = request.query_params.get('subject')
        if not subject:
            return Response({'subject': 'This query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'questions': integrations.fetch_trivia_questions(subject)})


class ResourceRecommendationsView(APIView):
    """Accepts the resource type as a path segment (/articles/) or as ?resource_type=."""

    def get(self, request, resource_type=None):
        subject = request.query_params.get('subject')
        if not subject:
            return Response({'subject': 'This query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        resource_type = resource_type or request.query_params.get('resource_type')
        return Response(integrations.search_core(subject, resource_type))


class GoogleAuthRedirectView(APIView):
    def get(self, request):
        return Response({
            'authorization_url': integrations.build_google_auth_url(request.user),
            'instructions': 'Open this URL in your browser within 10 minutes and allow access.',
        })


class GoogleAuthCallbackView(APIView):
    """Google redirects the browser here, so this request has no JWT; `state` identifies the user."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        if request.query_params.get('error'):
            return Response({'detail': f'Google login was cancelled: {request.query_params["error"]}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        code, state = request.query_params.get('code'), request.query_params.get('state')
        if not code or not state:
            return Response({'detail': 'Missing code or state.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(pk=integrations.user_id_from_state(state))
        except (signing.BadSignature, User.DoesNotExist):
            return Response({'detail': 'This login link is invalid or expired. Start again at /api/oauth/redirect/.'},
                            status=status.HTTP_400_BAD_REQUEST)
        integrations.connect_google_account(user, code)
        return Response({'message': 'Google account connected. You can close this tab and return to Postman.'})


class SendStudyNotesView(APIView):
    def post(self, request):
        serializer = serializers.SendStudyNotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = get_object_or_404(models.Note, pk=serializer.validated_data['note_id'], user=request.user)
        integrations.send_note_email(request.user, serializer.validated_data['to_email'], note)
        return Response({'message': 'Notes sent successfully via Gmail!'})


class AddExamToCalendarView(APIView):
    def post(self, request):
        serializer = serializers.ExamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        link = integrations.add_exam_event(
            request.user, data['subject'],
            datetime.combine(data['exam_date'], data['exam_time']), data['duration_minutes'],
        )
        return Response({'message': 'Exam added to Google Calendar successfully!', 'event_link': link},
                        status=status.HTTP_201_CREATED)
