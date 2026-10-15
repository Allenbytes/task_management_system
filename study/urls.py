from django.urls import re_path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views


def route(pattern, view, name):
    """Match with or without a trailing slash, as the Postman collection uses both."""
    return re_path(rf'^{pattern}/?$', view, name=name)


router = SimpleRouter()
router.trailing_slash = '/?'
router.register('tasks', views.TaskViewSet, basename='task')
router.register('subjects-lessons', views.SubjectLessonViewSet, basename='subject-lesson')
router.register('subjects-diary', views.SubjectDiaryViewSet, basename='subject-diary')
router.register('study-schedule', views.StudyScheduleViewSet, basename='study-schedule')
router.register('study-resources', views.StudyResourceViewSet, basename='study-resource')
router.register('study-break', views.StudyBreakViewSet, basename='study-break')
router.register('study-progress', views.StudyProgressViewSet, basename='study-progress')
router.register('study-challenges', views.StudyChallengeViewSet, basename='study-challenge')
router.register('study/quiz', views.QuizViewSet, basename='quiz')
router.register('study-prompt', views.StudyPromptViewSet, basename='study-prompt')
router.register('study-reflection', views.StudyReflectionViewSet, basename='study-reflection')
router.register('course-grades', views.CourseGradeViewSet, basename='course-grade')
router.register('notes', views.NoteViewSet, basename='note')

urlpatterns = [
    re_path(r'^$', views.HomeView.as_view(), name='home'),

    route('register', views.RegisterView.as_view(), 'register'),
    route('token', TokenObtainPairView.as_view(), 'token'),
    route('token/refresh', TokenRefreshView.as_view(), 'token-refresh'),
    route('logout', views.LogoutView.as_view(), 'logout'),

    route('generate-study-statistics', views.StudyStatisticsView.as_view(), 'study-statistics'),
    route(r'generate-study-schedule/(?P<schedule_id>\d+)/(?P<timer_id>\d+)',
          views.GenerateStudyScheduleView.as_view(), 'generate-study-schedule'),

    route('motivation', views.MotivationView.as_view(), 'motivation'),
    route('resources/quiz', views.TriviaQuizView.as_view(), 'trivia-quiz'),
    route(r'study-resources-recommendations(?:/(?P<resource_type>[\w-]+))?',
          views.ResourceRecommendationsView.as_view(), 'resource-recommendations'),

    route('oauth/redirect', views.GoogleAuthRedirectView.as_view(), 'google-oauth-redirect'),
    route('oauth/callback', views.GoogleAuthCallbackView.as_view(), 'google-oauth-callback'),
    route('send-study-notes', views.SendStudyNotesView.as_view(), 'send-study-notes'),
    route('add-exam-to-calendar', views.AddExamToCalendarView.as_view(), 'add-exam-to-calendar'),
] + router.urls
