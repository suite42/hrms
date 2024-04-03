// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.provide("hrms.hr");
frappe.provide("erpnext.accounts.dimensions");

frappe.ui.form.on('Expense Claim', {
	onload: function(frm) {
		erpnext.accounts.dimensions.setup_dimension_filters(frm, frm.doctype);
	
		if(frm.is_new()){
			frm.is_submit_and_cancel = 0
		}
		
		if(frm.doc.status === "Draft" && frm.doc.docstatus === 0 && (frm.doc.employee?.length || 0) === 0){
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
	company: function(frm) {
		erpnext.accounts.dimensions.update_dimension(frm, frm.doctype);
		var expenses = frm.doc.expenses;
		for (var i = 0; i < expenses.length; i++) {
			var expense = expenses[i];
			if (!expense.expense_type) {
				continue;
			}
			frappe.call({
				method: "hrms.hr.doctype.expense_claim.expense_claim.get_expense_claim_account_and_cost_center",
				args: {
					"expense_claim_type": expense.expense_type,
					"company": frm.doc.company
				},
				callback: function(r) {
					if (r.message) {
						expense.default_account = r.message.account;
						expense.cost_center = r.message.cost_center;
					}
				}
			});
		}
	},
});

frappe.ui.form.on('Expense Claim Detail', {
	expense_type: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		if (!frm.doc.company) {
			d.expense_type = "";
			frappe.msgprint(__("Please set the Company"));
			this.frm.refresh_fields();
			return;
		}

		if(!d.expense_type) {
			return;
		}
		return frappe.call({
			method: "hrms.hr.doctype.expense_claim.expense_claim.get_expense_claim_account_and_cost_center",
			args: {
				"expense_claim_type": d.expense_type,
				"company": frm.doc.company
			},
			callback: function(r) {
				if (r.message) {
					d.default_account = r.message.account;
					d.cost_center = r.message.cost_center;
				}
			}
		});
	}
});

cur_frm.add_fetch('employee', 'company', 'company');
cur_frm.add_fetch('employee','employee_name','employee_name');
cur_frm.add_fetch('expense_type','description','description');

cur_frm.cscript.refresh = function(doc) {
	cur_frm.cscript.set_help(doc);

	if(!doc.__islocal) {

		if (doc.docstatus===1) {
			/* eslint-disable */
			// no idea how `me` works here
			var entry_doctype, entry_reference_doctype, entry_reference_name;
			if(doc.__onload.make_payment_via_journal_entry){
				entry_doctype = "Journal Entry";
				entry_reference_doctype = "Journal Entry Account.reference_type";
				entry_reference_name = "Journal Entry.reference_name";
			} else {
				entry_doctype = "Payment Entry";
				entry_reference_doctype = "Payment Entry Reference.reference_doctype";
				entry_reference_name = "Payment Entry Reference.reference_name";
			}

			if (cint(doc.total_amount_reimbursed) > 0 && frappe.model.can_read(entry_doctype)) {
				cur_frm.add_custom_button(__('Bank Entries'), function() {
					frappe.route_options = {
						party_type: "Employee",
						party: doc.employee,
						company: doc.company
					};
					frappe.set_route("List", entry_doctype);
				}, __("View"));
			}
			/* eslint-enable */
		}
	}
};

cur_frm.cscript.set_help = function(doc) {
	cur_frm.set_intro("");
	if(doc.__islocal && !in_list(frappe.user_roles, "HR User")) {
		cur_frm.set_intro(__("Fill the form and save it"));
	}
};

cur_frm.cscript.validate = function(doc) {
	cur_frm.cscript.calculate_total(doc);
};

cur_frm.cscript.calculate_total = function(doc){
	doc.total_claimed_amount = 0;
	doc.total_sanctioned_amount = 0;
	$.each((doc.expenses || []), function(i, d) {
		doc.total_claimed_amount += d.amount;
		doc.total_sanctioned_amount += d.sanctioned_amount;
	});
};

cur_frm.cscript.calculate_total_amount = function(doc,cdt,cdn){
	cur_frm.cscript.calculate_total(doc,cdt,cdn);
};

cur_frm.fields_dict['cost_center'].get_query = function(doc) {
	return {
		filters: {
			"company": doc.company
		}
	}
};

erpnext.expense_claim = {
	set_title: function(frm) {
		if (!frm.doc.task) {
			frm.set_value("title", frm.doc.employee_name);
		}
		else {
			frm.set_value("title", frm.doc.employee_name + " for "+ frm.doc.task);
		}
	}
};

frappe.ui.form.on("Expense Claim", {
	setup: function(frm) {
		frm.add_fetch("company", "cost_center", "cost_center");
		frm.set_query("employee_advance", "advances", function() {
			return {
				filters: [
					['docstatus', '=', 1],
					['employee', '=', frm.doc.employee],
					['paid_amount', '>', 0],
					['status', 'not in', ['Claimed', 'Returned', 'Partly Claimed and Returned']]
				]
			};
		});

		frm.set_query("account_head", "taxes", function() {
			return {
				filters: [
					['company', '=', frm.doc.company],
					['account_type', 'in', ["Tax", "Chargeable", "Income Account", "Expenses Included In Valuation"]]
				]
			};
		});

		frm.set_query("payable_account", function() {
			return {
				filters: {
					"report_type": "Balance Sheet",
					"account_type": "Payable",
					"company": frm.doc.company,
					"is_group": 0
				}
			};
		});

		frm.set_query("task", function() {
			return {
				filters: {
					'project': frm.doc.project
				}
			};
		});

		frm.set_query("employee", function() {
			return {
				query: "erpnext.controllers.queries.employee_query"
			};
		});
	},

	currency: function(frm) {
		if(frm.doc.currency == "INR"){
			frappe.require('assets/hrms/js/child_table_utils.js', () => {
				makeColumnsReadOnly(frm, ["amount_in_user_currency"], "expenses");
			});
		}
	},

	refresh: function(frm) {
		frm.trigger("toggle_fields");

		if(frm.doc.status =="Draft" && frm.doc.docstatus ===0){
			frm.set_query('approver_1', () => {
				return {
					query: 'hrms.overrides.custom_employee_advance.get_all_managers',
				};
			});
		}

		if(frm.doc.status=="Pending Approval"){
			if(frm.doc.expense_category != "Business Expenses Outstation"){
				frm.toggle_display('mmt_id', false);
			}
		}

		$(frm.fields_dict["help_html"].wrapper).html(frappe.render_template("expense_claim_help"));

		var statusArray = ["Pending Payment", "Paid", "Cancelled"]
		if(frm.doc.docstatus > 0 && statusArray.includes(frm.doc.status)) {
			frm.add_custom_button(__('Accounting Ledger'), function() {
				frappe.route_options = {
					voucher_no: frm.doc.name,
					company: frm.doc.company,
					from_date: frm.doc.posting_date,
					to_date: moment(frm.doc.modified).format('YYYY-MM-DD'),
					group_by: '',
					show_cancelled_entries: frm.doc.docstatus === 2
				};
				frappe.set_route("query-report", "General Ledger");
			}, __("View"));
		}

		var submit_button_required = false;
		var cancel_button_requried = false;
		var doc_status = ["Pending Payment", "Paid", "Purchase Invoice Linked", "Pending Purchase Invoice"]
		if(!doc_status.includes(frm.doc.status) && !frm.is_dirty() && frm.doc.docstatus !==2){
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
		if(frm.doc.status === "Pending Payment"){
			frm.events.get_total_remaining_amount(frm)
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
							fieldtype: "Data",
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
							default: frm.doc.payable_account,
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
							label: __('Total Pending Amount (Including All the expense claim)'),
							fieldname: 'total_pending_amount',
							fieldtype: 'Currency',
							default: frm.fields_dict['total_pending_amount'].data,
							read_only: 1,
						},
						{
							label: __('Amount'),
							fieldname: 'paid_amount',
							fieldtype: 'Currency',
							reqd: 1,
						},
						{
							label: __('Expense Claim List'),
							fieldname: 'expense_claim_list',
							fieldtype: 'Data',
							default: frm.fields_dict['expense_claim_list'].default,
							read_only: 1
						}
					], function(values){
						var current_date = frappe.datetime.get_today()
						if (values.payment_date > current_date){
							frappe.throw("Payment Date cannot be a future Date")
						}
						frm.events.create_payment_entry(frm, values);
					},__("Enter Payment Details"))
				},__("Payment Details"))

			}).addClass("btn btn-primary btn-sm");
		}

		if(frm.doc.currency == "INR"){
			frappe.require('assets/hrms/js/child_table_utils.js', () => {
				removeColumns(frm, ["amount_in_user_currency"], "expenses");
			});
		}
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

	get_total_remaining_amount: function(frm){
		frappe.call({
			method: "hrms.overrides.custom_expense_claim.get_total_pending_amount",
			args: {
				doc_employee_name: frm.doc.employee_name,
			},
			callback: function(r) {
				if (r.message) {
					var total_pending_amount = 0;
					var expense_claim_list = [];
					r.message.forEach(function(row){
						total_pending_amount += row.grand_total
						expense_claim_list.push(row.name)
					});

					frm.fields_dict["expense_claim_list"] = {
						label: "Expense Claim List",
						fieldname: "expense_claim_list",
						fieldtype: 'Data',
						default: expense_claim_list
					}

					frm.fields_dict['total_pending_amount']={
						label: "Total Pending Amount",
						fieldname: "total_pending_amount",
						fieldtype: 'Currency',
						data: total_pending_amount,					
					}
					frm.refresh_fields("total_pending_amount")
					frm.refresh_fields("expense_claim_list")
					return r.message
				}
			}
		});	
	},


	create_payment_entry: function(frm, values){
		frappe.call({
			method: "hrms.overrides.custom_expense_claim.create_payment_entry",
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

	calculate_grand_total: function(frm) {
		var grand_total = flt(frm.doc.total_sanctioned_amount) + flt(frm.doc.total_taxes_and_charges) - flt(frm.doc.total_advance_amount);
		frm.set_value("grand_total", grand_total);
		frm.refresh_fields();
	},

	grand_total: function(frm) {
		frm.trigger("update_employee_advance_claimed_amount");
	},

	update_employee_advance_claimed_amount: function(frm) {
		let amount_to_be_allocated = frm.doc.grand_total;
		$.each(frm.doc.advances || [], function(i, advance){
			if (amount_to_be_allocated >= advance.unclaimed_amount){
				advance.allocated_amount = frm.doc.advances[i].unclaimed_amount;
				amount_to_be_allocated -= advance.allocated_amount;
			} else {
				advance.allocated_amount = amount_to_be_allocated;
				amount_to_be_allocated = 0;
			}
			frm.refresh_field("advances");
		});
	},

	make_payment_entry: function(frm) {
		let method = "hrms.overrides.employee_payment_entry.get_payment_entry_for_employee";
		if(frm.doc.__onload && frm.doc.__onload.make_payment_via_journal_entry) {
			method = "hrms.hr.doctype.expense_claim.expense_claim.make_bank_entry";
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

	is_paid: function(frm) {
		frm.trigger("toggle_fields");
	},

	toggle_fields: function(frm) {
		frm.toggle_reqd("mode_of_payment", frm.doc.is_paid);
	},

	employee_name: function(frm) {
		erpnext.expense_claim.set_title(frm);
	},

	task: function(frm) {
		erpnext.expense_claim.set_title(frm);
	},

	// employee: function(frm) {
	// 	frm.events.get_advances(frm);
	// },

	cost_center: function(frm) {
		frm.events.set_child_cost_center(frm);
	},

	validate: function(frm) {
		frm.events.set_child_cost_center(frm);
	},

	set_child_cost_center: function(frm){
		(frm.doc.expenses || []).forEach(function(d) {
			if (!d.cost_center){
				d.cost_center = frm.doc.cost_center;
			}
		});
	},
	get_taxes: function(frm) {
		if(frm.doc.taxes) {
			frappe.call({
				method: "calculate_taxes",
				doc: frm.doc,
				callback: () => {
					refresh_field("taxes");
					frm.trigger("update_employee_advance_claimed_amount");
				}
			});
		}
	},

	get_advances: function(frm) {
		frappe.model.clear_table(frm.doc, "advances");
		if (frm.doc.employee) {
			return frappe.call({
				method: "hrms.hr.doctype.expense_claim.expense_claim.get_advances",
				args: {
					employee: frm.doc.employee
				},
				callback: function(r, rt) {

					if(r.message) {
						$.each(r.message, function(i, d) {
							var row = frappe.model.add_child(frm.doc, "Expense Claim Advance", "advances");
							row.employee_advance = d.name;
							row.posting_date = d.posting_date;
							row.advance_account = d.advance_account;
							row.advance_paid = d.paid_amount;
							row.unclaimed_amount = flt(d.paid_amount) - flt(d.claimed_amount);
							row.allocated_amount = 0;
						});
						refresh_field("advances");
					}
				}
			});
		}
	}
});

frappe.ui.form.on("Expense Claim Detail", {
	amount: function(frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		// frappe.model.set_value(cdt, cdn, 'sanctioned_amount', child.amount);
	},

	sanctioned_amount: function(frm, cdt, cdn) {
		cur_frm.cscript.calculate_total(frm.doc, cdt, cdn);
		frm.trigger("get_taxes");
		frm.trigger("calculate_grand_total");
	},

	cost_center: function(frm, cdt, cdn) {
		erpnext.utils.copy_value_in_all_rows(frm.doc, cdt, cdn, "expenses", "cost_center");
	}
});

frappe.ui.form.on("Expense Claim Advance", {
	employee_advance: function(frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		if(!frm.doc.employee){
			frappe.msgprint(__('Select an employee to get the employee advance.'));
			frm.doc.advances = [];
			refresh_field("advances");
		}
		else {
			return frappe.call({
				method: "hrms.hr.doctype.expense_claim.expense_claim.get_advances",
				args: {
					employee: frm.doc.employee,
					advance_id: child.employee_advance
				},
				callback: function(r, rt) {
					if(r.message) {
						child.employee_advance = r.message[0].name;
						child.posting_date = r.message[0].posting_date;
						child.advance_account = r.message[0].advance_account;
						child.advance_paid = r.message[0].paid_amount;
						child.unclaimed_amount = flt(r.message[0].paid_amount) - flt(r.message[0].claimed_amount);
						child.allocated_amount = flt(r.message[0].paid_amount) - flt(r.message[0].claimed_amount);
						frm.trigger('calculate_grand_total');
						refresh_field("advances");
					}
				}
			});
		}
	}
});

frappe.ui.form.on("Expense Taxes and Charges", {
	account_head: function(frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		if(child.account_head && !child.description) {
			// set description from account head
			child.description = child.account_head.split(' - ').slice(0, -1).join(' - ');
			refresh_field("taxes");
		}
	},

	calculate_total_tax: function(frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		child.total = flt(frm.doc.total_sanctioned_amount) + flt(child.tax_amount);
		frm.trigger("calculate_tax_amount", cdt, cdn);
	},

	calculate_tax_amount: function(frm) {
		frm.doc.total_taxes_and_charges = 0;
		(frm.doc.taxes || []).forEach(function(d) {
			frm.doc.total_taxes_and_charges += d.tax_amount;
		});
		frm.trigger("calculate_grand_total");
	},

	rate: function(frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		if(!child.amount) {
			child.tax_amount = flt(frm.doc.total_sanctioned_amount) * (flt(child.rate)/100);
		}
		frm.trigger("calculate_total_tax", cdt, cdn);
	},

	tax_amount: function(frm, cdt, cdn) {
		frm.trigger("calculate_total_tax", cdt, cdn);
	}
});

