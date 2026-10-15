"""Pure study-planning logic, kept free of Django so it is easy to test and explain."""
from collections import defaultdict

DAY_START = 8 * 60        # first block starts at 08:00
DAY_END = 24 * 60         # the plan must finish by midnight
MEALS = [('lunch', 12 * 60), ('dinner', 18 * 60)]
MEAL_LENGTH = 60


class ScheduleError(ValueError):
    pass


def _clock(minutes):
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def build_study_plan(subjects, study_hours, study_minutes, break_minutes):
    """
    Split `study_hours` evenly across `subjects`, in blocks of `study_minutes`
    separated by `break_minutes` breaks. Lunch (12:00) and dinner (18:00) each
    take an hour; a block that would run into a meal is split around it.
    """
    if not subjects:
        raise ScheduleError('The study schedule has no subjects.')
    total = round(study_hours * 60)
    if total <= 0:
        raise ScheduleError('Study hours must be greater than zero.')

    plan = []
    clock = DAY_START
    meals = list(MEALS)

    def add(kind, subject, minutes):
        nonlocal clock
        while minutes > 0:
            if meals and clock >= meals[0][1]:
                name, _ = meals.pop(0)
                plan.append(_block(name, None, clock, MEAL_LENGTH))
                clock += MEAL_LENGTH
                if kind == 'break':
                    return  # the meal already serves as the break
                continue
            chunk = min(minutes, meals[0][1] - clock) if meals else minutes
            plan.append(_block(kind, subject, clock, chunk))
            clock += chunk
            minutes -= chunk

    base, extra = divmod(total, len(subjects))
    remaining = total
    for index, subject in enumerate(subjects):
        minutes = base + (1 if index < extra else 0)
        while minutes > 0:
            chunk = min(minutes, study_minutes)
            add('study', subject, chunk)
            minutes -= chunk
            remaining -= chunk
            if remaining > 0:
                add('break', subject, break_minutes)

    if clock > DAY_END:
        raise ScheduleError(
            f'{study_hours} study hours with these breaks and meals do not fit between 08:00 and midnight.'
        )
    return plan


def _block(kind, subject, start, minutes):
    return {
        'subject': subject,
        'type': kind,
        'start_time': _clock(start),
        'end_time': _clock(start + minutes),
        'duration_minutes': minutes,
    }


def study_statistics(grades, sessions):
    """
    grades: iterable of (course_name, grade) - averaged per course.
    sessions: iterable of (subject, hours) - summed per subject.
    """
    grade_lists = defaultdict(list)
    for course, grade in grades:
        grade_lists[course].append(grade)
    averages = {course: round(sum(g) / len(g), 2) for course, g in grade_lists.items()}

    hours = defaultdict(float)
    for subject, study_hours in sessions:
        hours[subject] += study_hours

    def pick(values, func, key):
        if not values:
            return None
        subject = func(values, key=values.get)
        return {'subject': subject, key: round(values[subject], 2)}

    return {
        'highest_grade': pick(averages, max, 'grade'),
        'lowest_grade': pick(averages, min, 'grade'),
        'most_studied_subject': pick(hours, max, 'study_hours'),
        'least_studied_subject': pick(hours, min, 'study_hours'),
    }
