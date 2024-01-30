import frappe
from frappe import _
from functools import wraps
from pymysql.err import IntegrityError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging
from hrms.suite42_utils.reimbursement_constants import TaskTypeConstatns
from frappe.desk.form.assign_to import add
from frappe.exceptions import (
    DuplicateEntryError,
    UniqueValidationError,
    MandatoryError,
    ValidationError,
)


def user_has_role(user, role):
    role_present = frappe.db.get_list(
        "Has Role", filters={"parent": user, "role": role}, ignore_permissions=True
    )
    return bool(role_present)


def get_last_date():
    current_date = datetime.now().date()
    if current_date.day <= 5:
        last_date_to_approve = current_date.replace(day=5).strftime("%Y-%m-%d")
    else:
        last_date_to_approve = (current_date.replace(day=5) + relativedelta(months=+1)).strftime(
            "%Y-%m-%d"
        )
    return last_date_to_approve


def create_reimbursement_task(
    project_name,
    task_type,
    link_doctype,
    link_docname,
    priority,
    suite42_lead,
    assigned_users,
):
    current_date = frappe.utils.today()
    exp_end_date = get_last_date()
    task = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": "{task_type} -- {link_docname}".format(
                link_docname=link_docname, task_type=task_type
            ),
            "project": project_name,
            "type": task_type,
            "exp_start_date": current_date,
            "exp_end_date": exp_end_date,
            "color": "#f5e105",
            "priority": priority,
            "suite42_lead": suite42_lead,
            "link_doctype": link_doctype,
            "link_docname": link_docname,
        }
    )
    task = task.insert()
    args = {
        "assign_to_me": 0,
        "assign_to": ["dinakar@suite42.in"],
        "date": task.exp_end_date,
        "priority": task.priority,
        "description": task.subject,
        "doctype": "Task",
        "name": task.name,
        "bulk_assign": "false",
        "re_assign": "false",
    }
    add(args)


def mark_tasks_as_completed(link_doctype, link_docname, task_type):
    task_name_list = frappe.get_list(
        "Task",
        filters={
            "link_doctype": link_doctype,
            "link_docname": link_docname,
            "status": [
                "not in",
                [TaskTypeConstatns.COMPLETED, TaskTypeConstatns.CANCELLED],
            ],
            "type": task_type,
        },
        pluck="name",
    )
    for task_name in task_name_list:
        task_doc = frappe.get_doc("Task", task_name)
        task_doc.status = TaskTypeConstatns.COMPLETED
        task_doc.completed_by = frappe.session.user
        task_doc.completed_on = frappe.utils.today()
        task_doc.save()


def handle_exceptions_with_readable_message(func):
    """
    Set readable message on failure
    """

    @wraps(func)
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DuplicateEntryError as e:
            args = e.args
            response = frappe.local.response
            if len(args) == 3:
                doctype = args[0]
                name = args[1]
                response["readable_message"] = f"DuplicateEntryError for {doctype}: {name}"
            else:
                response["readable_message"] = "DuplicateEntryError"
            raise e
        except UniqueValidationError as e:
            response = frappe.local.response
            args = e.args
            if isinstance(args[-1], IntegrityError):
                msg = e.args[-1].args[1]
                response["readable_message"] = f"UniqueValidationError: {msg}"
            else:
                response["readable_message"] = "UniqueValidationError"
            raise e
        except MandatoryError as e:
            response = frappe.local.response
            response["readable_message"] = f"MandatoryError, {e.args[0]}"
            raise e
        except ValidationError as e:
            response = frappe.local.response
            response["readable_message"] = f"ValidationError, {e.args[0]}"
            raise e
        except TypeError as e:
            response = frappe.local.response
            response["readable_message"] = f"TypeError, {e.args[0]}"
            raise e
        except Exception as e:
            response = frappe.local.response
            response["readable_message"] = "Internal Server Error"
            raise e

    return inner
