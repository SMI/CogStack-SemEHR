if (typeof qbb == "undefined"){
	var qbb = {};
}

(function($) {
	if(typeof qbb.inf == "undefined") {

		qbb.inf = {
			// Azure VM
			//service_url: "http://picturesdevab.uksouth.cloudapp.azure.com:8485/api",
			// Safe Haven
			//service_url: "http://10.0.2.135:8485/api"
			// Docker
			// not? service_url: "http://localhost:8080/api",
			//service_url: "https://localhost:8485/api",
			service_url: $(location).attr("href").replace("vis","api").slice(0,-1),
			// eleanor
			//service_url: "http://172.16.49.120:8000/api",

			getDocList: function(searchCB, passphrase){
				var sendObject= ["docs"];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			needPassphrase: function(searchCB, passphrase){
				var sendObject= ["need_passphrase"];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			checkPhrase: function(phrase, searchCB, passphrase){
				var sendObject= ["check_phrase", phrase];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			getDocDetail: function(docId, searchCB, passphrase){
				var sendObject= ["doc_detail", docId];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			getDocDetailMapping: function(docId, mapping, searchCB, passphrase){
				var sendObject= ["doc_content_mapping", docId, mapping];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			searchDocs: function(query, searchCB, passphrase){
				var sendObject= ["search_docs", query];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			searchAnns: function(query, searchCB, passphrase){
				var sendObject= ["search_anns", query];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			searchAnns2: function(query, searchCB, passphrase, queryDict){
				var sendObject= ["search_anns", query];
				qbb.inf.callAPI(sendObject, searchCB, passphrase, queryDict);
			},

			searchAnnsMapping: function(query, mapping, searchCB, passphrase){
				var sendObject= ["search_anns_by_mapping", query, mapping];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			getMappings: function(searchCB, passphrase){
				var sendObject= ["mappings"];
				qbb.inf.callAPI(sendObject, searchCB, passphrase);
			},

			callAPI: function(sendObject, cb, passphrase, queryDict){
				qbb.inf.ajax.doGet(sendObject, function(s){
					var ret = s;
					if (ret)
					{
						if (typeof cb == 'function')
							cb(ret);
					}else
					{
						if (typeof cb == 'function')
							cb();
					}
				}, function(){
					alert("Sorry, the request failed. Either the passphrase is incorrect, the server is not running, or an internal error occurred (API call failed). Please report to an administrator.");
				}, passphrase, queryDict);
			},

			ajax: {
					// Function parameters:
					// sendData - an array of string appended to the URL
					// success, error - functions called on success/failure
					// passphrase - the password
					// queryDict - optional dictionary sent as '?j=JSON' in URL
					doGet:function(sendData, success, error, passphrase, queryDict){
						var url = qbb.inf.service_url;
						for (var i=0;i<sendData.length;i++)
							url += "/" + sendData[i];
						if (sendData.length > 0)
							url += "/";
						if (passphrase)
							url += "?passphrase=" + passphrase;
						qbb.inf.ajax.doSend("Get", url, sendData, success, error, queryDict);
					},
					doPost:function(sendData,success,error){
						qbb.inf.ajax.doSend("Post",null,sendData,success,error);
					},
					doSend:function(method, url, sendData, success, error, queryDict){
						dataSuccess = function(data){
							(success)(eval(data));
						};
						if (sendData) sendData.token = "";
						if (queryDict) sendData = 'j='+JSON.stringify(queryDict);
						jQuery.ajax({
							   type: method || "Get",
							   url: url || qbb.inf.service_url,
							   data: sendData || [],
							   cache: false,
							   dataType: "jsonp", /* use "html" for HTML, use "json" for non-HTML */
							   success: dataSuccess /* (data, textStatus, jqXHR) */ || null,
							   error: error /* (jqXHR, textStatus, errorThrown) */ || null
						});
					}
			}
		};
	}
})(jQuery);
