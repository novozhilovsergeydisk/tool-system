# AGENTS.md - Tool System Project Guidelines

## Build/Lint/Test Commands
- **Run all tests**: `python manage.py test`
- **Run single test**: `python manage.py test inventory.tests.TestClass.test_method`
- **Run tests for specific app**: `python manage.py test inventory`
- **Run server**: `python manage.py runserver`
- **Make migrations**: `python manage.py makemigrations`
- **Apply migrations**: `python manage.py migrate`
- **Collect static files**: `python manage.py collectstatic`

## Code Style Guidelines

### Imports
- Standard library imports first, then Django imports, then third-party, then local imports
- Use `from django.shortcuts import render, redirect, get_object_or_404` style for multiple imports
- Group imports with blank lines between groups

### Naming Conventions
- **Models**: PascalCase (e.g., `ToolInstance`, `MovementLog`)
- **Fields**: snake_case (e.g., `current_holder`, `license_plate`)
- **Functions/Methods**: snake_case (e.g., `get_object_or_404`)
- **Variables**: snake_case (e.g., `today = date.today()`)
- **Constants**: UPPER_CASE (e.g., `TYPE_CHOICES`)

### Django Patterns
- Use `get_object_or_404()` for retrieving objects
- Use Django's built-in authentication decorators (`@login_required`, `@staff_member_required`)
- Use `messages` framework for user notifications
- Use `Paginator` for list views
- Use ModelForms for form handling

### Error Handling
- Use Django's form validation for user input
- Handle database errors gracefully with try/except blocks
- Use Django's `messages` for user-friendly error display

### Templates & Views
- Use class-based views where appropriate
- Keep business logic in views, presentation in templates
- Use Bootstrap classes for consistent styling
- Follow Django template naming conventions

### Database
- Use PostgreSQL in production
- Create proper migrations for model changes
- Use appropriate field types and constraints
- Follow Django ORM best practices

### Security
- Never commit secrets or API keys
- Use environment variables for sensitive data
- Validate all user inputs
- Use Django's built-in security features

## Agent Communication Guidelines
- Always respond in Russian language
- Use concise, direct responses
- Provide clear explanations for technical changes
- Follow project conventions and patterns