from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from . import models


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def create(self, validated_data):
        # create_user hashes the password
        return User.objects.create_user(**validated_data)


class OwnedMeta:
    """Shared Meta: the owner is set from the logged-in user, never from the request body."""
    exclude = ['user']


class TaskSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.Task


class SubjectLessonSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.SubjectLesson


class SubjectDiarySerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.SubjectDiary


class StudyScheduleSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.StudySchedule

    def validate_subjects(self, value):
        if not [s for s in value.split(',') if s.strip()]:
            raise serializers.ValidationError('Provide at least one subject.')
        return value


class StudyResourceSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.StudyResource


class StudyBreakSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.StudyBreak


class StudyProgressSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.StudyProgress


class StudyChallengeSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.StudyChallenge

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'End date cannot be before the start date.'})
        return attrs


class QuizSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.Quiz


class StudyPromptSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.StudyPrompt


class StudyReflectionSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.StudyReflection


class CourseGradeSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.CourseGrade


class NoteSerializer(serializers.ModelSerializer):
    class Meta(OwnedMeta):
        model = models.Note


class SendStudyNotesSerializer(serializers.Serializer):
    to_email = serializers.EmailField()
    note_id = serializers.IntegerField()


class ExamSerializer(serializers.Serializer):
    exam_date = serializers.DateField()
    exam_time = serializers.TimeField(input_formats=['%H:%M'])
    subject = serializers.CharField(max_length=100)
    duration_minutes = serializers.IntegerField(min_value=1, max_value=720, default=120)
