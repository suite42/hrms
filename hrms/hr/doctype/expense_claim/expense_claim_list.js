
function exportButtonFunction(listview) {
    console.log("export as csv ");
	frappe.prompt([
		{
			label: __('Company'),
			fieldname: 'company',
			fieldtype: 'Data',
			default: "One Suite Technologies Private Limited",
			read_only: 1
		},
		{
			label: __('Account'),
			fieldname: 'account',
			fieldtype: 'Link',
			options: "Bank Account",
			get_query: function() {
			return {
				filters: {
					"is_company_account": 1
				}
			};
    		}
		},
	], function(values){
		var url = "/api/method/hrms.hr.doctype.expense_claim.bulk_download.bulk_download"
		url += "?company=" + encodeURIComponent(values.company)
		url += "&account=" + encodeURIComponent(values.account)
		window.open(url)
	},__("Export"))
	
};

function importButtonFunction(listview){
	frappe.prompt([
		{
			label: __('File'),
			fieldname: 'import_file',
			fieldtype: 'Attach',
			reqd:1,
		},
	], function(values){

		frappe.call({
			method: "hrms.hr.doctype.expense_claim.bulk_payment.bulk_payment",
			args: {
                url: values.import_file
            },
			callback: function(r) {
				if(r.message){
					reload_doc();
					frappe.msgprint(__(r.message));
					return r.message
				}else{
					frappe.throw("Error While Doing Bulk Payment")
				}
				
			}
		});
	},__("Upload File"))
};


frappe.listview_settings['Expense Claim'] = {
	add_fields: ["total_claimed_amount", "docstatus", "company"],
	get_indicator: function(doc) {
		if(doc.status == "Paid") {
			return [__("Paid"), "green", "status,=,Paid"];
		}else if(doc.status == "Unpaid") {
			return [__("Unpaid"), "orange", "status,=,Unpaid"];
		} else if(doc.status == "Rejected") {
			return [__("Rejected"), "grey", "status,=,Rejected"];
		}
	},
	refresh: function(listview) {
		
        listview.page.add_inner_button("Export", function() {
            exportButtonFunction(listview);
        });
        listview.page.add_inner_button("Import", function() {
            importButtonFunction(listview);
        });
    },
};
