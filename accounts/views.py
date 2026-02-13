from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import role_required
from audit.models import AuditEvent
from audit.utils import log_event
from .forms import UserCreateForm, UserEditForm
from .models import User


@login_required
@role_required("admin")
def user_list(request):
    users = User.objects.filter(clinic=request.clinic).order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})


@login_required
@role_required("admin")
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.clinic = request.clinic
            user.save()
            log_event(
                request,
                action=AuditEvent.Action.USER_CREATED,
                obj=user,
                metadata={"username": user.username, "role": user.role},
            )
            messages.success(request, f'User "{user.username}" created successfully.')
            return redirect("accounts:list")
    else:
        form = UserCreateForm()
    return render(request, "accounts/user_form.html", {"form": form, "is_create": True})


@login_required
@role_required("admin")
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk, clinic=request.clinic)
    original_role = user.role  # capture before form.is_valid() mutates the instance

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            new_role = form.cleaned_data.get("role")
            new_active = form.cleaned_data.get("is_active")

            # Guard: admin cannot demote their own account
            if user.pk == request.user.pk and original_role == "admin" and new_role != "admin":
                form.add_error("role", "You cannot change your own admin role.")
                return render(request, "accounts/user_form.html", {"form": form, "is_create": False, "target_user": user})

            # Guard: don't remove last active admin
            if original_role == "admin" and new_role != "admin":
                active_admins = User.objects.filter(
                    clinic=request.clinic, role="admin", is_active=True
                ).count()
                if active_admins <= 1:
                    form.add_error("role", "Cannot change role — this is the only active admin in the clinic.")
                    return render(request, "accounts/user_form.html", {"form": form, "is_create": False, "target_user": user})

            # Guard: don't deactivate last active admin
            if original_role == "admin" and not new_active:
                active_admins = User.objects.filter(
                    clinic=request.clinic, role="admin", is_active=True
                ).count()
                if active_admins <= 1:
                    form.add_error("is_active", "Cannot deactivate — this is the only active admin in the clinic.")
                    return render(request, "accounts/user_form.html", {"form": form, "is_create": False, "target_user": user})

            form.save()
            log_event(
                request,
                action=AuditEvent.Action.USER_EDITED,
                obj=user,
                metadata={"username": user.username, "role": user.role},
            )
            messages.success(request, f'User "{user.username}" updated successfully.')
            return redirect("accounts:list")
    else:
        form = UserEditForm(instance=user)

    return render(request, "accounts/user_form.html", {"form": form, "is_create": False, "target_user": user})


@login_required
@role_required("admin")
def user_toggle_active(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden()

    user = get_object_or_404(User, pk=pk, clinic=request.clinic)

    # Guard: cannot deactivate yourself
    if user.pk == request.user.pk:
        return redirect("accounts:list")

    # Guard: cannot deactivate the last active admin
    if user.is_active and user.role == "admin":
        active_admins = User.objects.filter(
            clinic=request.clinic, role="admin", is_active=True
        ).count()
        if active_admins <= 1:
            return redirect("accounts:list")

    user.is_active = not user.is_active
    user.save()

    log_event(
        request,
        action=AuditEvent.Action.USER_DEACTIVATED,
        obj=user,
        metadata={"username": user.username, "is_active": user.is_active},
    )
    status = "activated" if user.is_active else "deactivated"
    messages.success(request, f'User "{user.username}" {status}.')
    return redirect("accounts:list")
