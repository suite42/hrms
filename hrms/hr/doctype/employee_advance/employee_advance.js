// Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
frappe.ui.form.on('Employee Advance', {
	onload: function(frm) {
		if(frm.doc.status === "Draft" && frm.doc.docstatus === 0){
			frappe.db.get_value("Employee", {"user_id": frappe.session.user}, ["name", "employee_name", "company"], function(response) {
				if (Object.keys(response).length !== 0) {
					frm.doc.employee = response["name"]
					frm.doc.employee_name = response["employee_name"]
					frm.doc.company = response["company"]
					frm.refresh_fields("employee")
					frm.refresh_fields("employee_name")
				}
			});
		}
	},

	setup: function(frm) {
		frm.add_fetch("employee", "company", "company");
		frm.add_fetch("company", "default_employee_advance_account", "advance_account");

		frm.set_query("employee", function() {
			return {
				filters: {
					"status": "Active"
				}
			};
		});

		frm.set_query("advance_account", function() {
			if (!frm.doc.employee) {
				frappe.msgprint(__("Please select employee first"));
			}
			let company_currency = erpnext.get_currency(frm.doc.company);
			let currencies = [company_currency];
			if (frm.doc.currency && (frm.doc.currency != company_currency)) {
				currencies.push(frm.doc.currency);
			}

			return {
				filters: {
					"root_type": "Asset",
					"is_group": 0,
					"company": frm.doc.company,
					"account_currency": ["in", currencies],
				}
			};
		});

		frm.set_query('salary_component', function() {
			return {
				filters: {
					"type": "Deduction"
				}
			};
		});
	},

	refresh: function(frm) {
		if(frm.doc.status =="Draft" && frm.doc.docstatus ===0){
			frm.set_query('approver_1', () => {
				return {
					query: 'hrms.overrides.custom_employee_advance.get_all_managers',
				};
			});
		}
		var submit_button_required = false;
		var cancel_button_requried = false;
		
		if(frm.doc.status !== "Pending Payment" && frm.doc.status !== "Paid" && frm.doc.status !== "Partly Claimed" && frm.doc.status !== "Claimed" && !frm.is_dirty() && frm.doc.docstatus !==2){
			submit_button_required = true
		}

		if(frm.doc.docstatus === 0 && !frm.is_dirty()){
			cancel_button_requried = true
		}
		frappe.require('assets/hrms/js/expense_button.js', () => {
			frappe.require('assets/hrms/js/expense_cancel_button.js', () => {
				if (submit_button_required) {
					add_submit_button(frm);
				}
				if (cancel_button_requried) {
					add_cancel_button(frm);
				}
			});
		});

		if(frm.doc.status === "Pending Payment" && frm.doc.currency == "INR"){
			frm.events.get_mode_of_payments(frm)
			frm.events.get_company_bank_accounts(frm)
			var modeOfPayment = null
			frm.add_custom_button(__("Pay"), function() {
				frappe.prompt([
					{
						label: __('Mode Of Payment'),
						fieldname: 'mode_payment',
						fieldtype: 'Select',
						options: frm.fields_dict['payments_mode'].options,
						reqd:1,
					}
				], function(values){
					var modeOfPayment = values.mode_payment
					var default_form_account="";
					if (modeOfPayment == "Cash"){
						default_form_account="Cash - Suite42"
						frm.fields_dict['from_account'].options.push(default_form_account)
					}
					frappe.prompt([
						{
							label: __('Mode Of Payment'),
							fieldname: 'mode_of_payment',
							fieldtype: 'Data',
							default: modeOfPayment,
							reqd:1,
							read_only: 1,
						},
						{
							label: __('Company Bank Account'),
							fieldname: 'from_account',
							fieldtype: 'Select',
							options: frm.fields_dict['from_account'].options,
							default: default_form_account,
							reqd:1,
						},
						{
							label: __('To Chart Account '),
							fieldname: 'to_chart_Account',
							fieldtype: 'Data',
							default: frm.doc.advance_account,
							reqd:1,
							read_only: 1
						},
						{
							label: __('Payment Date'),
							fieldname: 'payment_date',
							fieldtype: 'Date',
							reqd:1,
						},
						{
							label: __('Reference No'),
							fieldname: 'reference_no',
							fieldtype: 'Data',
							reqd:(modeOfPayment == "Cash")?0:1,
							hidden:(modeOfPayment == "Cash")?1:0
						},
						{
							label: __('Amount'),
							fieldname: 'total_amount',
							fieldtype: 'Currency',
							default: frm.doc.sanctioned_amount,
							read_only: 1,
						}
					], function(values){
						var current_date = frappe.datetime.get_today()
						if (values.payment_date > current_date){
							frappe.throw("Payment Date cannot be a future Date")
						}
						frm.events.create_payment_entry(frm, values);
						frm.refresh()
					},__("Enter Payment Details"))
				},__("Payment Details"))
			});
		}

	},

	get_company_bank_accounts: function(frm){
		frappe.call({
			method: "hrms.overrides.custom_expense_claim.get_company_bank_accounts",
			callback: function(r) {
				if (r.message) {
					frm.fields_dict['from_account']={
						label: "From Account",
						fieldname: "from_account",
						options: null,
					}
					frm.fields_dict['from_account'].options = r.message;
					frm.refresh_fields("from_account")
				}
			}
		});
	},


	get_mode_of_payments: function(frm){
		frappe.call({
			method: "hrms.overrides.custom_expense_claim.get_mode_of_payments",
			callback: function(r) {
				if (r.message) {
					frm.fields_dict['payments_mode']={
						label: "Payments Mode",
						fieldname: "payments_mode",
						options: null,
					}
					frm.fields_dict['payments_mode'].options = r.message;
					frm.refresh_fields("payments_mode")
				}
			}
		});
	},

	create_payment_entry: function(frm, values){
		frappe.call({
			method: "hrms.overrides.custom_employee_advance.create_payment_entry",
			args: {
				doc_name: frm.doc.name,
				values: values
			},
			callback: function(r) {
				frm.reload_doc();				
				return r.message
			}
		});
	},

	make_deduction_via_additional_salary: function(frm) {
		frappe.call({
			method: "hrms.hr.doctype.employee_advance.employee_advance.create_return_through_additional_salary",
			args: {
				doc: frm.doc
			},
			callback: function(r) {
				var doclist = frappe.model.sync(r.message);
				frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
			}
		});
	},

	make_payment_entry: function(frm) {
		let method = "hrms.overrides.employee_payment_entry.get_payment_entry_for_employee";
		if (frm.doc.__onload && frm.doc.__onload.make_payment_via_journal_entry) {
			method = "hrms.hr.doctype.employee_advance.employee_advance.make_bank_entry";
		}
		return frappe.call({
			method: method,
			args: {
				"dt": frm.doc.doctype,
				"dn": frm.doc.name
			},
			callback: function(r) {
				var doclist = frappe.model.sync(r.message);
				frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
			}
		});
	},

	make_expense_claim: function(frm) {
		return frappe.call({
			method: "hrms.hr.doctype.expense_claim.expense_claim.get_expense_claim",
			args: {
				"employee_name": frm.doc.employee,
				"company": frm.doc.company,
				"employee_advance_name": frm.doc.name,
				"posting_date": frm.doc.posting_date,
				"paid_amount": frm.doc.paid_amount,
				"claimed_amount": frm.doc.claimed_amount
			},
			callback: function(r) {
				const doclist = frappe.model.sync(r.message);
				frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
			}
		});
	},

	make_return_entry: function(frm) {
		frappe.call({
			method: 'hrms.hr.doctype.employee_advance.employee_advance.make_return_entry',
			args: {
				'employee': frm.doc.employee,
				'company': frm.doc.company,
				'employee_advance_name': frm.doc.name,
				'return_amount': flt(frm.doc.paid_amount - frm.doc.claimed_amount),
				'advance_account': frm.doc.advance_account,
				'mode_of_payment': frm.doc.mode_of_payment,
				'currency': frm.doc.currency,
				'exchange_rate': frm.doc.exchange_rate
			},
			callback: function(r) {
				const doclist = frappe.model.sync(r.message);
				frappe.set_route('Form', doclist[0].doctype, doclist[0].name);
			}
		});
	},

	employee: function(frm) {
		if (frm.doc.employee) {
			frappe.run_serially([
				// () => frm.trigger('get_employee_currency'),
				() => frm.trigger('get_pending_amount')
			]);
		}
	},

	get_pending_amount: function(frm) {
		frappe.call({
			method: "hrms.hr.doctype.employee_advance.employee_advance.get_pending_amount",
			args: {
				"employee": frm.doc.employee,
				"posting_date": frm.doc.posting_date
			},
			callback: function(r) {
				frm.set_value("pending_amount", r.message);
			}
		});
	},

	get_employee_currency: function(frm) {
		frappe.call({
			method: "hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment.get_employee_currency",
			args: {
				employee: frm.doc.employee,
			},
			callback: function(r) {
				if (r.message) {
					frm.set_value('currency', r.message);
					frm.refresh_fields();
				}
			}
		});
	},

	currency: function(frm) {
		if (frm.doc.currency) {
			var from_currency = frm.doc.currency;
			var company_currency;
			if (!frm.doc.company) {
				company_currency = erpnext.get_currency(frappe.defaults.get_default("Company"));
			} else {
				company_currency = erpnext.get_currency(frm.doc.company);
			}
			if (from_currency != company_currency) {
				frm.events.set_exchange_rate(frm, from_currency, company_currency);
			} else {
				frm.set_value("exchange_rate", 1.0);
				frm.set_df_property('exchange_rate', 'hidden', 1);
				frm.set_df_property("exchange_rate", "description", "");
			}
			frm.refresh_fields();
		}
	},

	set_exchange_rate: function(frm, from_currency, company_currency) {
		frappe.call({
			method: "erpnext.setup.utils.get_exchange_rate",
			args: {
				from_currency: from_currency,
				to_currency: company_currency,
			},
			callback: function(r) {
				frm.set_value("exchange_rate", flt(r.message));
				frm.set_df_property('exchange_rate', 'hidden', 0);
				frm.set_df_property("exchange_rate", "description", "1 " + frm.doc.currency +
					" = [?] " + company_currency);
			}
		});
	}
});

