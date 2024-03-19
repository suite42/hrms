from hrms.hr.doctype.expense_claim.expense_claim import ExpenseClaim
from erpnext.accounts.doctype.payment_entry.payment_entry import (
    get_party_details,
    get_account_details,
)
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

from hrms.suite42_utils.common_functions import (
    user_has_role,
    handle_exceptions_with_readable_message,
    create_reimbursement_task,
    mark_tasks_as_completed,
)

from hrms.suite42_utils.reimbursement_constants import (
    RoleConstants,
    ExpenseClaimConstants,
    CompanyConstants,
    EmployeeConstant,
    TaskTypeConstatns,
    ExpenseCategoryConstants,
)

from frappe.query_builder.functions import Sum
from frappe.utils import cstr, flt, get_link_to_form
import frappe
from frappe import _
import json
from datetime import datetime


class CustomExpenseClaim(ExpenseClaim):
    def validate(self):
        self.validate_employee_type()
        if self.is_overriden:
            self.check_expense_date()
        self.calculate_total_amount()
        self.validate_sanctioned_amount()
        self.validate_advances()
        self.state_transition_check()
        self.calculate_grand_total()

        old_doc = self.get_doc_before_save()
        if old_doc is not None and old_doc.status == self.status:
            if self.status == "Draft":
                if frappe.session.user != self.owner:
                    frappe.throw(_("Only Owner can edit in Draft State"))
                if self.expense_category_flow == "Flow2":
                    self.set("advances", [])
                    if self.mmt_id:
                        frappe.throw(
                            _(
                                f"MMT Record Cannot be attached for expense category {self.expense_category}"
                            )
                        )
            elif self.status == "Pending Approval":
                if not (
                    frappe.session.user == self.approver_1
                    or frappe.session.user == "Administrator"
                ):
                    frappe.throw(_("Only the Added approver can edit the document"))
                if (
                    old_doc.total_sanctioned_amount == self.total_sanctioned_amount
                    and old_doc.total_advance_amount == self.total_advance_amount
                ):
                    frappe.throw(
                        _(
                            f"Only allowed to edit sanction and advance amount in {self.status} state"
                        )
                    )
        else:
            self.add_approver()
            self.payable_account = CompanyConstants.PAYABLE_ACCOUNTS[self.company][
                "reimbursement_payable_account"
            ]
        if self.expense_category_flow == "Flow1" and (
            not old_doc or old_doc.mmt_id != self.mmt_id
        ):
            self.set("advances", [])
            self.add_advances()
        self.validate_approver()
        self.validate_mmit_id()

    def add_approver(self):
        employee_doc = frappe.get_doc("Employee", self.employee)
        if self.total_claimed_amount > RoleConstants.ADVANCE_AMOUNT:
            self.approver_1 = employee_doc.expense_approver_2
        else:
            self.approver_1 = employee_doc.expense_approver

    def validate_mmit_id(self):
        if self.expense_category in ExpenseCategoryConstants.EXPENSE_CATEGORY_LIST:
            if not self.mmt_id:
                frappe.throw(
                    _(
                        f"MMT Record should be attached for Expense category {self.expense_category}"
                    )
                )

    def validate_employee_type(self):
        employee_doc = frappe.get_doc("Employee", self.employee)
        if employee_doc.employment_type == EmployeeConstant.CONTRACT_EMPLOYEE_TYPE:
            if not employee_doc.supplier:
                frappe.throw(
                    _(
                        "Cannot create Expense Claim since there is no supplier attached to this employee"
                    )
                )
            elif self.expense_category_flow == "Flow2":
                frappe.throw(
                    _(f"Not allowed to create for expense category - {self.expense_category}")
                )
        elif employee_doc.employment_type not in EmployeeConstant.EMPLOYEMENT_TYPE:
            frappe.throw(
                _(f"{employee_doc.employment_type} Employement Type cannot create Expense Claim ")
            )

    def check_expense_date(self):
        current_date = datetime.now().date()
        current_month = current_date.month
        current_date = current_date.replace(month=current_month - 1, day=5)
        for expense in self.expenses:
            expense_date = datetime.strptime(str(expense.expense_date), "%Y-%m-%d").date()
            if expense_date < current_date:
                frappe.throw(
                    _(f"Expense Date Cannot be before  {current_date.strftime('%Y-%m-%d')}")
                )
            if expense_date > datetime.now().date():
                frappe.throw(_("Cannot Have Future Dated Expenses"))

    def state_transition_check(self):
        if self.expense_category_flow == "Flow1":
            self.state_transtition_check_for_flow1()
        elif self.expense_category_flow == "Flow2":
            self.state_transtition_check_for_flow2()
        else:
            frappe.throw(
                _(f"No state tansition check present for the flow {self.expense_category_flow}")
            )

    def calculate_grand_total(self):
        self.grand_total = flt(self.total_sanctioned_amount) - flt(self.total_advance_amount)
        self.round_floats_in(self, ["grand_total"])

    def on_update_after_submit(self):
        self.state_transition_check()
        old_doc = self.get_doc_before_save()
        self.total_advance_amount = 0
        for d in self.get("advances"):
            self.total_advance_amount += flt(d.allocated_amount)
        if old_doc.total_advance_amount != self.total_advance_amount:
            self.update_claimed_amount_in_employee_advance()
            self.db_set("total_advance_amount", self.total_advance_amount)
        self.grand_total = flt(self.total_sanctioned_amount) - flt(self.total_advance_amount)
        self.round_floats_in(self, ["grand_total"])
        self.db_set("grand_total", self.grand_total)

    def state_transtition_check_for_flow2(self):
        old_doc = self.get_doc_before_save()
        if old_doc is not None and old_doc.status != self.status:
            if self.status == ExpenseClaimConstants.PENDING_APPROVAL:
                if old_doc.status not in [ExpenseClaimConstants.DRAFT]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if frappe.session.user != self.owner:
                    frappe.throw(_("Only Owner can request Approval in draft state"))
                create_reimbursement_task(
                    None,
                    TaskTypeConstatns.APPROVE_EXPENSE_CLAIM,
                    "Expense Claim",
                    self.name,
                    None,
                    None,
                    [self.approver_1],
                )

                frappe.share.add_docshare(
                    "Expense Claim",
                    self.name,
                    self.approver_1,
                    read=1,
                    write=1,
                    flags={"ignore_share_permission": True},
                )
            elif self.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L1:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_APPROVAL]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not (
                    frappe.session.user == self.approver_1
                    or frappe.session.user == "Administrator"
                ):
                    frappe.throw(_(f"Only the Added approver or Admin can approve the document"))
                mark_tasks_as_completed(
                    "Expense Claim", self.name, TaskTypeConstatns.APPROVE_EXPENSE_CLAIM
                )
            elif self.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L2:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L1]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not user_has_role(frappe.session.user, RoleConstants.HR_L1_EXPENSE_ROLE):
                    frappe.throw(
                        _(
                            f"Only user with role {RoleConstants.HR_L1_EXPENSE_ROLE} approve the document"
                        )
                    )
            elif self.status == ExpenseClaimConstants.PENDING_PAYMENT:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L2]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not user_has_role(frappe.session.user, RoleConstants.HR_L2_EXPENSE_ROLE):
                    frappe.throw(
                        _("Only user having HR L2 Expense Approver role can approve the document")
                    )
                self.make_gl_entries()
            elif self.status == ExpenseClaimConstants.PAID:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_PAYMENT]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not user_has_role(frappe.session.user, RoleConstants.FINANCE_ROLE):
                    frappe.throw(
                        _(
                            f"Invalid permission, only user with role {RoleConstants.FINANCE_ROLE} is allowed"
                        )
                    )
            elif self.status == ExpenseClaimConstants.CANCELLED:
                if old_doc.status not in [
                    ExpenseClaimConstants.DRAFT,
                    ExpenseClaimConstants.PENDING_APPROVAL,
                    ExpenseClaimConstants.PENDING_PAYMENT,
                    ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L1,
                    ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L2,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if (
                    old_doc.status == ExpenseClaimConstants.DRAFT
                    and not frappe.session.user != self.owner
                ):
                    frappe.throw(_(f"Can be Canceled by Owner Only"))
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_APPROVAL
                    and frappe.session.user != "Administrator"
                    and frappe.session.user != self.approver_1
                ):
                    frappe.throw(_(f"Can be Canceled either by {self.approver_1} or by Admin"))
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L1
                    and not user_has_role(frappe.session.user, RoleConstants.HR_L1_EXPENSE_ROLE)
                ):
                    frappe.throw(
                        _(
                            f"Only user having {RoleConstants.HR_L1_EXPENSE_ROLE} can cancel the document"
                        )
                    )
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L2
                    and not user_has_role(frappe.session.user, RoleConstants.HR_L2_EXPENSE_ROLE)
                ):
                    frappe.throw(
                        _(
                            f"Only user having {RoleConstants.HR_L2_EXPENSE_ROLE} can cancel the document"
                        )
                    )
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_PAYMENT
                    and frappe.session.user != "Administrator"
                ):
                    frappe.throw(_("Only Admin can cancel in Pending Payment State"))
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_PAYMENT
                    and frappe.session.user == "Administrator"
                ):
                    self.ignore_linked_doctypes = (
                        "GL Entry",
                        "Stock Ledger Entry",
                        "Payment Ledger Entry",
                    )
                    if self.payable_account:
                        self.make_gl_entries(cancel=True)
            else:
                frappe.throw(_("Unhandelled State Transition"))

    def state_transtition_check_for_flow1(self):
        old_doc = self.get_doc_before_save()
        if old_doc is not None and old_doc.status != self.status:
            employee_doc = frappe.get_doc("Employee", self.employee)
            if self.status == ExpenseClaimConstants.PENDING_APPROVAL:
                if old_doc.status not in [ExpenseClaimConstants.DRAFT]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if frappe.session.user != self.owner:
                    frappe.throw(_("Only Owner can request Approval in draft state"))
                create_reimbursement_task(
                    None,
                    TaskTypeConstatns.APPROVE_EXPENSE_CLAIM,
                    "Expense Claim",
                    self.name,
                    None,
                    None,
                    [self.approver_1],
                )
                frappe.share.add_docshare(
                    "Expense Claim",
                    self.name,
                    self.approver_1,
                    read=1,
                    write=1,
                    flags={"ignore_share_permission": True},
                )
            elif self.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L1:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_APPROVAL]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not (
                    frappe.session.user == self.approver_1
                    or frappe.session.user == "Administrator"
                ):
                    frappe.throw(_("Only the added approver can approve the document"))

                mark_tasks_as_completed(
                    "Expense Claim", self.name, TaskTypeConstatns.APPROVE_EXPENSE_CLAIM
                )
            elif self.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L1]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not user_has_role(frappe.session.user, RoleConstants.OFFICE_ADMIN_L1_ROLE):
                    frappe.throw(
                        _(
                            f"Only user with role {RoleConstants.OFFICE_ADMIN_L1_ROLE} approve the document"
                        )
                    )
            elif self.status == ExpenseClaimConstants.PENDING_PAYMENT:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if not user_has_role(frappe.session.user, RoleConstants.OFFICE_ADMIN_L2_ROLE):
                    frappe.throw(
                        _(
                            f"Only user having {RoleConstants.OFFICE_ADMIN_L2_ROLE} role can approve the document"
                        )
                    )
                self.make_gl_entries()
            elif self.status == ExpenseClaimConstants.PENDING_PURCHASE_INVOICE:
                if old_doc.status not in [
                    ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2,
                    ExpenseClaimConstants.PURCHASE_INVOICE_LINKED,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if (
                    old_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2
                    and not user_has_role(frappe.session.user, RoleConstants.OFFICE_ADMIN_L2_ROLE)
                ):
                    frappe.throw(
                        _("Only user having HR L2 Expense Approver role can approve the document")
                    )
            elif self.status == ExpenseClaimConstants.PURCHASE_INVOICE_LINKED:
                if old_doc.status not in [ExpenseClaimConstants.PENDING_PURCHASE_INVOICE]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
            elif self.status == ExpenseClaimConstants.PAID:
                if old_doc.status not in [
                    ExpenseClaimConstants.PENDING_PAYMENT,
                    ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if old_doc.status in [ExpenseClaimConstants.PENDING_PAYMENT]:
                    if not user_has_role(frappe.session.user, RoleConstants.FINANCE_ROLE):
                        frappe.throw(
                            _(
                                f"Invalid permission, only user with role {RoleConstants.FINANCE_ROLE} is allowed"
                            )
                        )
            elif self.status == ExpenseClaimConstants.CANCELLED:
                if old_doc.status not in [
                    ExpenseClaimConstants.DRAFT,
                    ExpenseClaimConstants.PENDING_APPROVAL,
                    ExpenseClaimConstants.PENDING_PAYMENT,
                    ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L1,
                    ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2,
                    ExpenseClaimConstants.PENDING_PURCHASE_INVOICE,
                    ExpenseClaimConstants.PURCHASE_INVOICE_LINKED,
                ]:
                    frappe.throw(_(f"Invalid State Transition to state {self.status}"))
                if (
                    old_doc.status == ExpenseClaimConstants.DRAFT
                    and not frappe.session.user == self.owner
                ):
                    frappe.throw(_(f"Can be Canceled by Owner Only"))
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_APPROVAL
                    and frappe.session.user != "Administrator"
                    and frappe.session.user != self.approver_1
                ):
                    frappe.throw(_(f"Can be Canceled either by {self.approver_1} or by Admin"))
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L1
                    and not user_has_role(frappe.session.user, RoleConstants.OFFICE_ADMIN_L1_ROLE)
                ):
                    frappe.throw(
                        _(
                            f"Only user having {ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L1} can cancel the document"
                        )
                    )
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2
                    and not user_has_role(frappe.session.user, RoleConstants.OFFICE_ADMIN_L2_ROLE)
                ):
                    frappe.throw(
                        _(
                            f"Only user having {RoleConstants.OFFICE_ADMIN_L2_ROLE} can cancel the document"
                        )
                    )
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_PAYMENT
                    and frappe.session.user != "Administrator"
                ):
                    frappe.throw(
                        _(
                            f"Only Admin can cancel in {ExpenseClaimConstants.PENDING_PAYMENT} State"
                        )
                    )
                elif (
                    old_doc.status
                    in [
                        ExpenseClaimConstants.PENDING_PURCHASE_INVOICE,
                        ExpenseClaimConstants.PURCHASE_INVOICE_LINKED,
                    ]
                    and frappe.session.user != "Administrator"
                ):
                    frappe.throw(_(f"Only Admin can cancel in {old_doc.status} State"))
                elif (
                    old_doc.status == ExpenseClaimConstants.PENDING_PAYMENT
                    and frappe.session.user == "Administrator"
                ):
                    self.ignore_linked_doctypes = (
                        "GL Entry",
                        "Stock Ledger Entry",
                        "Payment Ledger Entry",
                    )
                    if self.payable_account:
                        self.make_gl_entries(cancel=True)
            else:
                frappe.throw(_("Unhandelled State Transition"))

    def add_advances(self):
        advances_list = []
        employee_advance_list = frappe.db.get_list(
            "Employee Advance",
            filters={
                "status": ["in", ["Partly Claimed", "Paid"]],
                "employee": self.employee,
                "mmt_id": self.mmt_id if self.mmt_id else ["is", "not set"],
            },
            pluck="name",
            ignore_permissions=True,
        )
        if employee_advance_list:
            for row in employee_advance_list:
                employee_advance_doc = frappe.get_doc("Employee Advance", row)
                advances_entry = {
                    "docstatus": 0,
                    "doctype": "Expense Claim Advance",
                    "parent": self.name,
                    "parentfield": "advances",
                    "parenttype": "Expense Claim",
                    "idx": 1,
                    "employee_advance": employee_advance_doc.name,
                    "posting_date": employee_advance_doc.posting_date.strftime("%Y-%m-%d"),
                    "advance_account": employee_advance_doc.advance_account,
                    "advance_paid": employee_advance_doc.paid_amount,
                    "unclaimed_amount": employee_advance_doc.paid_amount
                    - employee_advance_doc.claimed_amount,
                    "allocated_amount": 0,
                }
                advances_list.append(advances_entry)
                self.append("advances", advances_entry)

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

        if self.total_claimed_amount >= RoleConstants.EXPENSE_AMOUNT and not user_has_role(
            self.approver_1, RoleConstants.EXPENSE_APPROVER2_ROLE
        ):
            frappe.throw(
                _(
                    f"Select L2 Level Approval since the amount is greater than or equal to {RoleConstants.EXPENSE_AMOUNT}"
                )
            )
        elif not (
            user_has_role(self.approver_1, RoleConstants.EXPENSE_APPROVER1_ROLE)
            or user_has_role(self.approver_1, RoleConstants.EXPENSE_APPROVER2_ROLE)
        ):
            frappe.throw(
                _(
                    f"Approval selected does not have L1 or L2 Expense Approver Role since the amount is less than or equal to {RoleConstants.EXPENSE_AMOUNT}"
                )
            )

    def calculate_total_amount(self):
        self.total_claimed_amount = 0
        self.total_sanctioned_amount = 0

        for d in self.get("expenses"):
            self.round_floats_in(d)

            self.total_claimed_amount += flt(d.amount)
            self.total_sanctioned_amount += flt(d.sanctioned_amount)

        self.round_floats_in(self, ["total_claimed_amount", "total_sanctioned_amount"])

    def validate_sanctioned_amount(self):
        if self.status == ExpenseClaimConstants.PENDING_APPROVAL:
            for d in self.get("expenses"):
                if flt(d.sanctioned_amount) > flt(d.amount):
                    frappe.throw(
                        _(
                            "Sanctioned Amount cannot be greater than Claim Amount in Row {0}."
                        ).format(d.idx)
                    )
            if self.total_sanctioned_amount == 0:
                frappe.throw(_("Sanctioned Amount cannot be zero"))

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
            frappe.throw(_("Cannot Create Expense Claim For Other User"))

    def on_cancel(self):
        self.status = ExpenseClaimConstants.CANCELLED
        self.state_transition_check()
        self.update_claimed_amount_in_employee_advance()
        self.db_set("status", ExpenseClaimConstants.CANCELLED)

    # overriding as update_reimbursed_amount function is calling to set status
    def set_status(self, update=False):
        pass

    # overriding as default implementation is sharing the doc with the approver
    def on_update(self):
        pass

    def on_submit(self):
        if self.is_submit_and_cancel:
            self.cancel()
        else:
            self.update_claimed_amount_in_employee_advance()

    @frappe.whitelist()
    def cancel_doc(self):
        self.is_submit_and_cancel = 1
        self.status = ExpenseClaimConstants.CANCELLED
        self.save(ignore_permissions=True)
        self.submit()


@frappe.whitelist()
@handle_exceptions_with_readable_message
def next_state(doc_name):
    expense_claim_doc = frappe.get_doc("Expense Claim", doc_name)
    if expense_claim_doc.expense_category_flow == "Flow1":
        if expense_claim_doc.status == ExpenseClaimConstants.DRAFT:
            expense_claim_doc.status = ExpenseClaimConstants.PENDING_APPROVAL
            expense_claim_doc.save()
        elif expense_claim_doc.status == ExpenseClaimConstants.PENDING_APPROVAL:
            expense_claim_doc.status = ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L1
            expense_claim_doc.save(ignore_permissions=True)
            expense_claim_doc.submit()
        elif expense_claim_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L1:
            expense_claim_doc.status = ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2
            expense_claim_doc.save()
        elif expense_claim_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_ADMIN_L2:
            employee_doc = frappe.get_doc("Employee", expense_claim_doc.employee)
            if employee_doc.employment_type == EmployeeConstant.CONTRACT_EMPLOYEE_TYPE:
                expense_claim_doc.status = ExpenseClaimConstants.PENDING_PURCHASE_INVOICE
            elif expense_claim_doc.grand_total == 0:
                expense_claim_doc.status = ExpenseClaimConstants.PAID
            else:
                expense_claim_doc.status = ExpenseClaimConstants.PENDING_PAYMENT
            expense_claim_doc.save()
        else:
            frappe.throw(_("Unhandelled State Transition"))
    elif expense_claim_doc.expense_category_flow == "Flow2":
        if expense_claim_doc.status == ExpenseClaimConstants.DRAFT:
            expense_claim_doc.status = ExpenseClaimConstants.PENDING_APPROVAL
            expense_claim_doc.save()
        elif expense_claim_doc.status == ExpenseClaimConstants.PENDING_APPROVAL:
            expense_claim_doc.status = ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L1
            expense_claim_doc.save(ignore_permissions=True)
            expense_claim_doc.submit()
        elif expense_claim_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L1:
            expense_claim_doc.status = ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L2
            expense_claim_doc.save()
        elif expense_claim_doc.status == ExpenseClaimConstants.PENDING_APPROVAL_BY_HR_L2:
            expense_claim_doc.status = ExpenseClaimConstants.PENDING_PAYMENT
            expense_claim_doc.save()
        else:
            frappe.throw(_("Unhandelled State Transition"))
    else:
        frappe.throw(
            _(f"No State Transiton Present for Flow {expense_claim_doc.expense_category_flow}")
        )
    return f"Successfully transitioned to the State {expense_claim_doc.status}"


@frappe.whitelist()
@handle_exceptions_with_readable_message
def get_total_pending_amount(doc_employee_name):
    expense_claims = frappe.db.get_list(
        "Expense Claim",
        filters={"status": "Pending Payment", "employee_name": doc_employee_name},
        fields=["grand_total", "name"],
    )
    return expense_claims


@frappe.whitelist()
@handle_exceptions_with_readable_message
def get_mode_of_payments():
    return frappe.db.get_list("Mode of Payment", pluck="name", ignore_permissions=True)


@frappe.whitelist()
@handle_exceptions_with_readable_message
def get_company_bank_accounts():
    return frappe.db.get_list(
        "Bank Account",
        filters={"company": CompanyConstants.SUITE42, "currency": "INR", "is_company_account": 1},
        pluck="name",
        ignore_permissions=True,
    )


@frappe.whitelist()
@handle_exceptions_with_readable_message
def create_payment_entry(doc_name, values):
    if not user_has_role(frappe.session.user, RoleConstants.FINANCE_ROLE):
        frappe.throw(_("Only Finance Team can make a Payment entry"))

    doc = frappe.get_doc("Expense Claim", doc_name)

    payment_values = frappe._dict(json.loads(values))

    if payment_values.paid_amount <= 0:
        frappe.throw(_("Paid Amount should be greater than 0"))

    if payment_values.mode_of_payment != "Cash":
        payment_date = datetime.strptime(payment_values.payment_date, "%Y-%m-%d").date()

    party_details = get_party_details(
        doc.company, "Employee", doc.employee, frappe.utils.nowdate()
    )

    employee_doc = frappe.get_doc("Employee", doc.employee)

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

    bank_cash_account = bank_cash_doc.name
    bank_account_currency = bank_cash_doc.account_currency

    paid_to = doc.payable_account
    paid_to_account_currency = get_account_details(paid_to, frappe.utils.nowdate()).get(
        "account_currency"
    )

    reference_list = []
    total_pending_amount = 0
    for name in payment_values.expense_claim_list:
        expense_claim_doc = frappe.get_doc("Expense Claim", name)
        expense_claim_details_dates = frappe.db.get_list(
            "Expense Claim Detail",
            filters={"parent": expense_claim_doc.name},
            fields=["expense_date"],
            pluck="expense_date",
        )

        max_date = max(expense_claim_details_dates)
        if payment_date < max_date:
            frappe.throw(_(f"Payment Date should me more than the max of expenses date for expense claim {expense_claim_doc.name}"))

        total_pending_amount += expense_claim_doc.grand_total
        remaining_amount = (
            expense_claim_doc.grand_total - expense_claim_doc.total_amount_reimbursed
        )
        reference_entry = {
            "reference_doctype": "Expense Claim",
            "reference_name": expense_claim_doc.name,
            "total_amount": expense_claim_doc.grand_total,
            "outstanding_amount": remaining_amount,
            "allocated_amount": remaining_amount,
            "parentfield": "references",
            "parenttype": "Payment Entry",
            "docstatus": 1,
            "doctype": "Payment Entry Reference",
        }
        reference_list.append(reference_entry)

        if expense_claim_doc.payable_account != paid_to:
            frappe.throw(
                _(
                    f"Payable account of {expense_claim_doc.name} not matching with the other reimbursement claim"
                )
            )

    if total_pending_amount != payment_values.paid_amount:
        frappe.throw(_("Total Paid Amount is not Matching with Pending Amount"))

    payment_entry_doc = frappe.get_doc(
        {
            "doctype": "Payment Entry",
            "docstatus": 1,
            "payment_type": "Pay",
            "mode_of_payment": payment_values.mode_of_payment,
            "party_type": "Employee",
            "party": doc.employee,
            "party_name": doc.employee_name,
            "paid_from": bank_cash_account,
            "paid_from_account_currency": bank_account_currency,
            "paid_to": paid_to,
            "paid_to_account_currency": paid_to_account_currency,
            "paid_amount": payment_values.paid_amount,
            "total_allocated_amount": payment_values.paid_amount,
            "received_amount": payment_values.paid_amount,
            "unallocated_amount": 0,
            "references": reference_list,
            "reference_no": payment_values.reference_no,
            "reference_date": payment_values.payment_date,
        }
    )
    doc = payment_entry_doc.insert(ignore_permissions=True)

    for name in payment_values.expense_claim_list:
        expense_claim_doc = frappe.get_doc("Expense Claim", name)
        expense_claim_doc.is_paid = 1
        expense_claim_doc.status = ExpenseClaimConstants.PAID
        expense_claim_doc.total_amount_reimbursed = expense_claim_doc.grand_total
        expense_claim_doc.save(ignore_permissions=True)

    return f"Payment Done Successfullly with the Payment Entry {doc.name}"
