from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class OwnedModel(models.Model):
    """Base for every record that belongs to a single user."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class Task(OwnedModel):
    task = models.CharField(max_length=255)
    goal_date = models.DateField()
    status = models.BooleanField(default=False)

    def __str__(self):
        return self.task


class SubjectLesson(OwnedModel):
    subject = models.CharField(max_length=100)
    lesson = models.TextField()


class SubjectDiary(OwnedModel):
    subject = models.CharField(max_length=100)
    note = models.TextField()

    class Meta(OwnedModel.Meta):
        verbose_name_plural = 'subject diaries'


class StudySchedule(OwnedModel):
    study_date = models.DateField()
    study_hours = models.FloatField(validators=[MinValueValidator(0.1), MaxValueValidator(24)])
    subjects = models.CharField(max_length=500, help_text='Comma-separated list of subjects.')

    def subject_list(self):
        return [s.strip() for s in self.subjects.split(',') if s.strip()]


class StudyResource(OwnedModel):
    title = models.CharField(max_length=255)
    url = models.URLField(max_length=500)
    subject = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=50)


class StudyBreak(OwnedModel):
    """A study/break timer, both durations in minutes."""
    study_duration = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    break_duration = models.PositiveIntegerField(validators=[MinValueValidator(1)])


class StudyProgress(OwnedModel):
    study_session_date = models.DateField()
    subject = models.CharField(max_length=100)
    completed = models.BooleanField(default=False)
    study_hours = models.FloatField(validators=[MinValueValidator(0)])

    class Meta(OwnedModel.Meta):
        verbose_name_plural = 'study progress'


class StudyChallenge(OwnedModel):
    challenge_description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()


class Quiz(OwnedModel):
    subject = models.CharField(max_length=100)
    quiz_content = models.TextField()

    class Meta(OwnedModel.Meta):
        verbose_name_plural = 'quizzes'


class StudyPrompt(OwnedModel):
    subject = models.CharField(max_length=100)
    prompt = models.TextField()


class StudyReflection(OwnedModel):
    reflection_date = models.DateField()
    strengths = models.TextField()
    areas_for_improvement = models.TextField()


class CourseGrade(OwnedModel):
    course_name = models.CharField(max_length=100)
    grade = models.FloatField(validators=[MinValueValidator(0)])


class Note(OwnedModel):
    subject = models.CharField(max_length=100)
    note_content = models.TextField()


class GoogleCredential(models.Model):
    """OAuth tokens that let the API act on a user's Gmail and Google Calendar."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='google_credential')
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    expires_at = models.DateTimeField()
    scopes = models.TextField(blank=True, help_text='Space-separated scopes Google granted.')
