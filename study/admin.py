from django.contrib import admin

from . import models

admin.site.register([
    models.Task, models.SubjectLesson, models.SubjectDiary, models.StudySchedule,
    models.StudyResource, models.StudyBreak, models.StudyProgress, models.StudyChallenge,
    models.Quiz, models.StudyPrompt, models.StudyReflection, models.CourseGrade, models.Note,
])


@admin.register(models.GoogleCredential)
class GoogleCredentialAdmin(admin.ModelAdmin):
    list_display = ['user', 'expires_at', 'scopes']
    exclude = ['access_token', 'refresh_token']  # never display secrets
