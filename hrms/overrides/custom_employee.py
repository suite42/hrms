import frappe
from frappe import _
from frappe.model.naming import set_name_by_naming_series
from frappe.utils import add_years, cint, get_link_to_form, getdate
from erpnext.setup.doctype.employee.employee import Employee
from hrms.suite42_utils.reimbursement_constants import (
    RoleConstants,
)


class CustomEmployee(Employee):
    def validate(self):
        super(CustomEmployee, self).validate()
        old_doc = self.get_doc_before_save()
        user_role_list = frappe.db.get_list(
            "Has Role",
            filters={"parent": self.user_id},
            fields=["role"],
            pluck="role",
            ignore_permissions=True,
        )
        excluded_role_present = False
        for role in user_role_list:
            if role in RoleConstants.REMOVE_USER_PERMISSIONS_FOR_ROLES:
                excluded_role_present = True
                break
        if excluded_role_present:
            self.create_user_permission = 0
            user_permissions_list = frappe.db.get_list(
                "User Permission",
                filters={"user": self.user_id, "allow": ["in", ["Employee", "Company"]]},
                pluck="name",
                ignore_permissions=True,
            )
            for perm in user_permissions_list:
                frappe.delete_doc("User Permission", user_permissions_list)
        else:
            self.create_user_permission = 1
