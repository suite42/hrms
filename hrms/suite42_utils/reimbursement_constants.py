class RoleConstants:
    EXPENSE_APPROVER1_ROLE = "L1 Expense Approver"
    EXPENSE_APPROVER2_ROLE = "L2 Expense Approver"
    HR_L1_EXPENSE_ROLE = "HR L1 Expense Approver"
    HR_L2_EXPENSE_ROLE = "HR L2 Expense Approver"
    FINANCE_ROLE = "Finance Team Expense Approver"
    OFFICE_ADMIN_L1_ROLE = "Office Admin L1 Expense Approver"
    OFFICE_ADMIN_L2_ROLE = "Office Admin L2 Expense Approver"
    EXPENSE_AMOUNT = 5000
    ADVANCE_AMOUNT = 5000
    EXPENSE_APPROVE_DATE = 5
    REMOVE_USER_PERMISSIONS_FOR_ROLES = [
        "HR L1 Expense Approver",
        "HR L2 Expense Approver",
        "Finance Team Expense Approver",
        "Office Admin L1 Expense Approver",
        "Office Admin L2 Expense Approver",
    ]


class CompanyConstants:
    S42_IDR = "PT. ONE SUITE TECHNOLOGIES"
    SUITE42 = "One Suite Technologies Private Limited"
    KOTAK_BANK = "Kotak Mahindra Bank"
    REIMBURSEMENT_BANK_ACCOUNT = ["5946999821"]
    PAYABLE_ACCOUNTS = {
        "PT. ONE SUITE TECHNOLOGIES": {
            "advance_payable_account": "Employee Advances - S42_IDR",
            "reimbursement_payable_account": "Reimbursement Payable - S42_IDR",
        },
        "One Suite Technologies Private Limited": {
            "advance_payable_account": "Employee Advances - Suite42",
            "reimbursement_payable_account": "Reimbursement Payable - Suite42",
        },
    }


class TaskTypeConstatns:
    APPROVE_EXPENSE_CLAIM = "Approve Expense Claim"
    APPROVE_EMPLOYEE_ADVANCE = "Approve Employee Advance"
    OPEN = "Open"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    ONHOLD = "OnHold"


class EmployeeConstant:
    EMPLOYEMENT_TYPE = ["Intern", "Full-time", "Probation"]
    CONTRACT_EMPLOYEE_TYPE = "Contract"


class ExpenseCategoryConstants:
    EXPENSE_CATEGORY_LIST = ["Business Expenses Outstation"]


class ExpenseClaimConstants:
    DRAFT = "Draft"
    PENDING_APPROVAL = "Pending Approval"
    PENDING_APPROVAL_BY_ADMIN_L1 = "Pending Approval By Admin L1"
    PENDING_APPROVAL_BY_ADMIN_L2 = "Pending Approval By Admin L2"
    PENDING_APPROVAL_BY_HR_L1 = "Pending Approval By HR L1"
    PENDING_APPROVAL_BY_HR_L2 = "Pending Approval By HR L2"
    PENDING_PURCHASE_INVOICE = "Pending Purchase Invoice"
    PURCHASE_INVOICE_LINKED = "Purchase Invoice Linked"
    PENDING_PAYMENT = "Pending Payment"
    CANCELLED = "Cancelled"
    PAID = "Paid"


class EmployeeAdvanceConstants:
    DRAFT = "Draft"
    PENDING_APPROVAL = "Pending Approval"
    PENDING_APPROVAL_BY_ADMIN_L2 = "Pending Approval By Admin L2"
    PENDING_APPROVAL_BY_HR = "Pending Approval By HR"
    PENDING_PAYMENT = "Pending Payment"
    CLAIMED = "Claimed"
    PARTLY_CLAIMED = "Partly Claimed"
    CANCELLED = "Cancelled"
    PAID = "Paid"
    ALLOWED_AMOUNT_PER_DAY = 1000
