from hrms.hr.doctype.employee_advance.employee_advance import EmployeeAdvance
from erpnext.accounts.doctype.payment_entry.payment_entry import (
    get_party_details,
    get_account_details,
)
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

from hrms.suite42_utils.common_functions import (
    user_has_role,
    handle_exceptions_with_readable_message,
    create_reimbursement_task,
    mark_tasks_as_completed,
)

from hrms.suite42_utils.reimbursement_constants import (
    RoleConstants,
    EmployeeAdvanceConstants,
    CompanyConstants,
    EmployeeConstant,
    TaskTypeConstatns,
    ExpenseCategoryConstants,
)

from frappe.utils import cstr, flt
import frappe
from frappe import _
import json
from datetime import datetime, timedelta


class CustomEmployeeAdvance(EmployeeAdvance):
    def validate(self):
        self.validate_employee_type()
        self.state_transtition_check()
        self.validate_mmit_id()
        self.validate_travel_date()
        # used when we are updating the document in a state
        old_doc = self.get_doc_before_save()
        if old_doc is not None and old_doc.status == self.status:
            if self.status == "Draft":
                if frappe.session.user != self.owner:
                    frappe.throw(_("Only Owner can edit in Draft State"))
            elif self.status == "Pending Approval":
                if not (
                    frappe.session.user == self.approver_1
                    or frappe.session.user == "Administrator"
                ):
                    frappe.throw(_("Only the Added approver can edit the document"))
                self.check_sanctioned_amount()

        self.advance_account = CompanyConstants.PAYABLE_ACCOUNTS[self.company][
            "advance_payable_account"
        ]
        self.add_approver()
        self.validate_approver()
        self.calulate_inr_amount()

    def add_approver(self):
        employee_doc = frappe.get_doc("Employee", self.employee)
        if self.advance_amount >= RoleConstants.ADVANCE_AMOUNT:
            self.approver_1 = employee_doc.expense_approver_2
        else:
            self.approver_1 = employee_doc.expense_approver

    def validate_travel_date(self):
        from_date = datetime.strptime(str(self.from_date), "%Y-%m-%d")
        to_date = datetime.strptime(str(self.to_date), "%Y-%m-%d")
        if from_date > to_date:
            frappe.throw(_("From Date should be less than To Date"))

    def check_advance_amount(self):
        from_date = datetime.strptime(str(self.from_date), "%Y-%m-%d")
        to_date = datetime.strptime(str(self.to_date), "%Y-%m-%d")
        no_of_days = to_date.day - from_date.day + 1
        amount_allowed_for_the_current_trip = (
            no_of_days * EmployeeAdvanceConstants.ALLOWED_AMOUNT_PER_DAY
        )
        old_doc = self.get_doc_before_save()
        if old_doc.status == EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2:
            if self.sanctioned_amount > amount_allowed_for_the_current_trip:
                if not self.is_date_override:
                    frappe.throw(
                        _(
                            f"Sanctioned amount {self.sanctioned_amount} should be less than total amount {amount_allowed_for_the_current_trip} allowed for {no_of_days} Days, select the Date override checkbox before approving"
                        )
                    )

    def check_approver_is_owner(self):
        if self.owner == frappe.session.user and frappe.session.user != "Administrator":
            frappe.throw(_("Cannot Approve/Cancel Your Own Employee Advance"))

    def validate_mmit_id(self):
        if self.expense_category in ExpenseCategoryConstants.EXPENSE_CATEGORY_LIST:
            if not self.mmt_id:
                frappe.throw(
                    _(
                        f'Travel Request ID should be attached for Expense category "{self.expense_category}"'
                    )
                )
        else:
            if self.mmt_id:
                frappe.throw(
                    _(
                        f'Travel Request ID should not be attached for Expense category "{self.expense_category}"'
                    )
                )

    def validate_employee_type(self):
        employee_doc = frappe.get_doc("Employee", self.employee)
        if employee_doc.employment_type not in EmployeeConstant.EMPLOYEMENT_TYPE:
            frappe.throw(
                _(f"{employee_doc.employment_type} Employement Type cannot create expense_claim")
            )

    def on_update_after_submit(self):
        self.state_transtition_check()
        self.check_advance_amount()

    def state_transtition_check(self):
        old_doc = self.get_doc_before_save()
        if old_doc is not None and old_doc.status != self.status:
            if self.status == EmployeeAdvanceConstants.PENDING_APPROVAL:
                if old_doc.status not in [EmployeeAdvanceConstants.DRAFT]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if frappe.session.user != self.owner:
                    frappe.throw(_("Only Owner can request Approval in draft state"))
                create_reimbursement_task(
                    None,
                    TaskTypeConstatns.APPROVE_EMPLOYEE_ADVANCE,
                    "Employee Advance",
                    self.name,
                    None,
                    None,
                    [self.approver_1],
                )
                frappe.share.add_docshare(
                    "Employee Advance",
                    self.name,
                    self.approver_1,
                    read=1,
                    write=1,
                    flags={"ignore_share_permission": True},
                )
                self.check_advance_amount()
            elif self.status == EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2:
                if old_doc.status not in [EmployeeAdvanceConstants.PENDING_APPROVAL]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not (
                    frappe.session.user == self.approver_1
                    or frappe.session.user == "Administrator"
                ):
                    frappe.throw(_("Only the Added approver can approve"))
                mark_tasks_as_completed(
                    "Employee Advance", self.name, TaskTypeConstatns.APPROVE_EMPLOYEE_ADVANCE
                )
                employee_bank_details = frappe.db.get_value(
                    "Bank Account",
                    {"party_type": "Employee", "party": self.employee},
                    ["bank_account_no", "ifsc"],
                )
                if employee_bank_details:
                    self.employee_bank_account_no = employee_bank_details[0]
                    self.employee_bank_ifsc = employee_bank_details[0]
                self.check_advance_amount()
            elif self.status == EmployeeAdvanceConstants.PENDING_PAYMENT:
                if old_doc.status not in [EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not user_has_role(frappe.session.user, RoleConstants.OFFICE_ADMIN_L2_ROLE):
                    frappe.throw(
                        _(
                            f"Only user having {RoleConstants.OFFICE_ADMIN_L2_ROLE} Role can approve the document"
                        )
                    )
                self.check_approver_is_owner()
                self.check_advance_amount()
            elif self.status == EmployeeAdvanceConstants.PAID:
                if old_doc.status not in [
                    EmployeeAdvanceConstants.PENDING_PAYMENT,
                    EmployeeAdvanceConstants.PARTLY_CLAIMED,
                    EmployeeAdvanceConstants.CLAIMED,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if (
                    old_doc.status == EmployeeAdvanceConstants.PENDING_PAYMENT
                    and not user_has_role(frappe.session.user, RoleConstants.FINANCE_ROLE)
                ):
                    frappe.throw(
                        _(
                            f"Invalid permission, only user with role {RoleConstants.FINANCE_ROLE} is allowed"
                        )
                    )
            elif self.status == EmployeeAdvanceConstants.PARTLY_CLAIMED:
                if old_doc.status not in [
                    EmployeeAdvanceConstants.CLAIMED,
                    EmployeeAdvanceConstants.PAID,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
            elif self.status == EmployeeAdvanceConstants.CLAIMED:
                if old_doc.status not in [
                    EmployeeAdvanceConstants.PARTLY_CLAIMED,
                    EmployeeAdvanceConstants.PAID,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
            elif self.status == EmployeeAdvanceConstants.CANCELLED:
                if old_doc.status not in [
                    EmployeeAdvanceConstants.DRAFT,
                    EmployeeAdvanceConstants.PENDING_APPROVAL,
                    EmployeeAdvanceConstants.PENDING_PAYMENT,
                    EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if (
                    old_doc.status == EmployeeAdvanceConstants.DRAFT
                    and not frappe.session.user == self.owner
                ):
                    frappe.throw(_(f"Can be Canceled by Owner Only"))
                elif (
                    old_doc.status == EmployeeAdvanceConstants.PENDING_APPROVAL
                    and frappe.session.user != "Administrator"
                    and frappe.session.user != self.approver_1
                ):
                    frappe.throw(_(f"Can be Canceled either by {self.approver_1} or by Admin"))
                elif old_doc.status == EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2:
                    self.check_approver_is_owner()
                elif (
                    old_doc.status == EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2
                    and not user_has_role(frappe.session.user, RoleConstants.OFFICE_ADMIN_L2_ROLE)
                ):
                    frappe.throw(
                        _(
                            f"Only user having {RoleConstants.OFFICE_ADMIN_L2_ROLE} can cancel the document"
                        )
                    )
                elif (
                    old_doc.status == EmployeeAdvanceConstants.PENDING_PAYMENT
                    and frappe.session.user != "Administrator"
                ):
                    frappe.throw(_("Only Admin can cancel in Pending Payment State"))
            else:
                frappe.throw(
                    _(f"Unhandelled State Transition from {old_doc.status} to {self.status}")
                )

    def check_sanctioned_amount(self):
        if self.status == EmployeeAdvanceConstants.PENDING_APPROVAL:
            if self.sanctioned_amount > self.advance_amount:
                frappe.throw(_("Cannot put Sanctioned amount more than the advanced amount"))
            if self.sanctioned_amount == 0:
                frappe.throw(_("sanctioned amount cannot be zero"))

    def validate_approver(self):
        user_id = frappe.get_list(
            "Employee",
            filters={"name": self.employee},
            fields=["user_id"],
            pluck="user_id",
            ignore_permissions=True,
        )
        if user_id:
            if user_id[0] == self.approver_1:
                frappe.throw(_("Employee and its Approver cannot be the same"))
        else:
            frappe.throw(_(f"User Id not Found for the  Employee {self.employee}"))

        if self.advance_amount >= RoleConstants.ADVANCE_AMOUNT and not user_has_role(
            self.approver_1, RoleConstants.EXPENSE_APPROVER2_ROLE
        ):
            frappe.throw(
                _(
                    f"Select L2 Level Approval since the amount is greater than or equal to {RoleConstants.ADVANCE_AMOUNT}"
                )
            )
        elif not (
            user_has_role(self.approver_1, RoleConstants.EXPENSE_APPROVER1_ROLE)
            or user_has_role(self.approver_1, RoleConstants.EXPENSE_APPROVER2_ROLE)
        ):
            frappe.throw(_(f"Approval selected does not have L1 or L2 Expense Approver Role"))

    def calulate_inr_amount(self):
        if self.currency != "INR":
            self.advance_amt_inr = flt(self.exchange_rate*self.advance_amount, 1)

    def update_claimed_amount(self):
        claimed_amount = (
            frappe.db.sql(
                """
            SELECT sum(ifnull(allocated_amount, 0))
            FROM `tabExpense Claim Advance` eca, `tabExpense Claim` ec
            WHERE
                eca.employee_advance = %s
                AND ec.name = eca.parent
                AND ec.docstatus=1
                AND eca.allocated_amount > 0
        """,
                self.name,
            )[0][0]
            or 0
        )

        self.claimed_amount = claimed_amount
        if self.claimed_amount == self.sanctioned_amount:
            self.status = EmployeeAdvanceConstants.CLAIMED
        elif self.claimed_amount != 0:
            self.status = EmployeeAdvanceConstants.PARTLY_CLAIMED
        elif self.paid_amount:
            self.status = EmployeeAdvanceConstants.PAID
        self.save(ignore_permissions=True)

    def before_insert(self):
        employee_id = frappe.get_list(
            "Employee",
            filters={"user_id": frappe.session.user},
            pluck="name",
            ignore_permissions=True,
        )
        if frappe.session.user != "Administrator" and (
            employee_id and employee_id[0] != self.employee
        ):
            frappe.throw(_("Cannot Create Employee Advance For Other User"))

    def set_status(self, update=False):
        pass

    def on_submit(self):
        if self.status != EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2:
            frappe.throw(_(f"Cannot Submit in state {self.status}"))
        if self.is_submit_and_cancel:
            self.cancel()

    def on_cancel(self):
        self.status = EmployeeAdvanceConstants.CANCELLED
        self.state_transtition_check()
        self.db_set("status", EmployeeAdvanceConstants.CANCELLED)

    @frappe.whitelist()
    def cancel_doc(self):
        self.is_submit_and_cancel = 1
        self.status = EmployeeAdvanceConstants.CANCELLED
        self.save(ignore_permissions=True)
        self.submit()


@frappe.whitelist()
@handle_exceptions_with_readable_message
def get_all_managers(doctype, txt, searchfield, start, page_len, filters):
    if doctype != "User":
        frappe.throw(_(f"Unhandled doctype: {doctype}"))

    filters = [
        [
            "Has Role",
            "role",
            "in",
            [RoleConstants.EXPENSE_APPROVER1_ROLE, RoleConstants.EXPENSE_APPROVER2_ROLE],
        ]
    ]
    txt = txt.strip()
    if txt:
        filters.append(["name", "like", f"%{txt}%"])
    managers_list = set(
        frappe.get_list(
            "User",
            filters=filters,
            fields=["name"],
            as_list=True,
            ignore_permissions=True,
        )
    )
    return managers_list


@frappe.whitelist()
@handle_exceptions_with_readable_message
def next_state(doc_name):
    employee_advance_doc = frappe.get_doc("Employee Advance", doc_name)
    if employee_advance_doc.status == EmployeeAdvanceConstants.DRAFT:
        employee_advance_doc.status = EmployeeAdvanceConstants.PENDING_APPROVAL
        employee_advance_doc.save()
    elif employee_advance_doc.status == EmployeeAdvanceConstants.PENDING_APPROVAL:
        employee_advance_doc.status = EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2
        employee_advance_doc.save(ignore_permissions=True)
        employee_advance_doc.submit()
    elif employee_advance_doc.status == EmployeeAdvanceConstants.PENDING_APPROVAL_BY_ADMIN_L2:
        employee_advance_doc.status = EmployeeAdvanceConstants.PENDING_PAYMENT
        employee_advance_doc.save(ignore_permissions=True)
    else:
        frappe.throw(_("Unhandelled State Transition"))
    return f"Successfully transitioned to the State {employee_advance_doc.status}"


@frappe.whitelist()
@handle_exceptions_with_readable_message
def check_sanctioned_amount_is_above_limit(frm_date, to_date, sanctioned_amount):
    from_date = datetime.strptime(str(frm_date), "%Y-%m-%d")
    to__date = datetime.strptime(str(to_date), "%Y-%m-%d")
    no_of_days = to__date.day - from_date.day + 1
    amount_allowed_for_the_current_trip = (
        no_of_days * EmployeeAdvanceConstants.ALLOWED_AMOUNT_PER_DAY
    )
    if int(sanctioned_amount) > amount_allowed_for_the_current_trip:
        return True
    else:
        return False


@frappe.whitelist()
@handle_exceptions_with_readable_message
def create_payment_entry(doc_name, values):
    if not user_has_role(frappe.session.user, RoleConstants.FINANCE_ROLE):
        frappe.throw(_("Only Finance Team can make a Payment entry"))

    employee_advance_doc = frappe.get_doc("Employee Advance", doc_name)

    payment_values = frappe._dict(json.loads(values))

    if payment_values.total_amount <= 0:
        frappe.throw(_("Paid Amount should be greater than 0"))

    current_date = datetime.now()
    current_month = current_date.month
    current_date = current_date.replace(month=current_month - 1, day=5)

    payment_date = datetime.strptime(payment_values.payment_date, "%Y-%m-%d")
    if payment_date < current_date:
        frappe.throw(_(f"Payment Date Cannot be before  {current_date.strftime('%Y-%m-%d')}"))

    bank = None
    bank_account = None
    bank_account_no = None
    if payment_values.mode_of_payment == "Cash":
        bank_cash_doc = frappe.get_doc("Account", payment_values.from_account)
    else:
        company_bank_account_doc = frappe.get_doc("Bank Account", payment_values.from_account)
        if (
            not company_bank_account_doc.is_company_account
            or company_bank_account_doc.bank_account_no
            not in CompanyConstants.REIMBURSEMENT_BANK_ACCOUNT
        ):
            frappe.throw(_("Company bank account selected is not supported"))
        bank_cash_doc = frappe.get_doc("Account", company_bank_account_doc.account)
        bank = company_bank_account_doc.bank
        bank_account = company_bank_account_doc.name
        bank_account_no = company_bank_account_doc.bank_account_no

    bank_cash_account = bank_cash_doc.name
    bank_account_currency = bank_cash_doc.account_currency

    paid_to = employee_advance_doc.advance_account

    paid_to_account_currency = get_account_details(paid_to, frappe.utils.nowdate()).get(
        "account_currency"
    )

    employee_bank_account = frappe.db.get_list(
        "Bank Account",
        filters={"party_type": "Employee", "party": employee_advance_doc.employee},
        pluck="name",
        ignore_permissions=True,
    )

    if not employee_bank_account:
        frappe.throw(_("Please Create Employee Bank Account First to create a payment entry"))
    employee_bank_account = employee_bank_account[0]

    payment_entry = frappe.get_doc(
        {
            "doctype": "Payment Entry",
            "docstatus": 1,
            "payment_type": "Pay",
            "mode_of_payment": payment_values.mode_of_payment,
            "party_type": "Employee",
            "party": employee_advance_doc.employee,
            "party_name": employee_advance_doc.employee_name,
            "party_bank_account": employee_bank_account,
            "paid_from": bank_cash_account,
            "paid_from_account_currency": bank_account_currency,
            "paid_to": payment_values.to_chart_Account,
            "paid_to_account_currency": paid_to_account_currency,
            "paid_amount": employee_advance_doc.sanctioned_amount,
            "total_allocated_amount": employee_advance_doc.sanctioned_amount,
            "received_amount": employee_advance_doc.sanctioned_amount,
            "unallocated_amount": 0,
            "references": [
                {
                    "reference_doctype": "Employee Advance",
                    "reference_name": employee_advance_doc.name,
                    "total_amount": employee_advance_doc.sanctioned_amount,
                    "outstanding_amount": employee_advance_doc.sanctioned_amount,
                    "allocated_amount": employee_advance_doc.sanctioned_amount,
                    "parentfield": "references",
                    "parenttype": "Payment Entry",
                    "docstatus": 1,
                    "doctype": "Payment Entry Reference",
                }
            ],
            "reference_no": payment_values.reference_no,
            "reference_date": payment_values.payment_date,
            "bank": bank,
            "bank_account": bank_account,
            "bank_account_no": bank_account_no,
        }
    )
    payment_entry_doc = payment_entry.insert(ignore_permissions=True)
    employee_advance_doc.reload()
    employee_advance_doc.status = EmployeeAdvanceConstants.PAID
    employee_advance_doc.save(ignore_permissions=True)
    return f"Payment Done Successfullly with the Payment Entry {payment_entry_doc.name}"
