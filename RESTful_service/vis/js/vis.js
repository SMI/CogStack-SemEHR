(function($){
    let _curDoc = null;
    let _curMapping = null;
    let _needPassphrase = false;
    let _passphrase = null;
    let _docTable = null;

    function checkPassphraseNecessary(){
        qbb.inf.needPassphrase(function (s){
            if (s){
                _needPassphrase = true;
                _passphrase = forge_sha256(prompt("Please enter the password:"));
                checkPhraseAndGO(_passphrase);
            }else
                start();
        }, _passphrase);
    }

    function start(){
        $('#klsearch').prop( "disabled", false );
        getAvailableMappings();
        getAllDocIds();
        toggleAnn();
    }

    function checkPhraseAndGO(phrase){
        qbb.inf.checkPhrase(phrase, function (ret){
            if (ret){
                start();
            }else{
                _passphrase = forge_sha256(prompt("Password not valid, please enter it again:"));
                checkPhraseAndGO(_passphrase);
            }
        }, _passphrase)
    }

    function getAvailableMappings(){
        qbb.inf.getMappings(function (ss){
            console.log("mappings:-", ss);
            let s = "mappings:";
            for (const m of ss){
                s += "<span name='" + m + "'>" + m + "</span>";
            }
            $(".mappings").html(s);

            $(".mappings span").click(function (){
                if ($(this).hasClass("selected")){
                    $(".mappings span").removeClass("selected");
                    _curMapping = null;
                }else{
                    $(".mappings span").removeClass("selected");
                    _curMapping = $(this).attr("name");
                    $(this).addClass("selected");
                }
                getDocDetail(_curDoc);
            });
        }, _passphrase);
    }

    function renderDocTable(docs){
        let s = "";
        for(let i=0; i<docs.length;i++){
            s += "<tr><td><a id='" + docs[i].replaceAll(".", "_") + "' docId='" + docs[i] + "'>" + docs[i] + "</a></td></tr>";
            if (i == 0){
                _curDoc = docs[i];
            }
        }
        $('.docList').html("<table id='docListTab' class=\"display\"><thead><tr><th>doc ids</th></tr></thead>" + s + "</table>");
        $('.docList a').click(function (){
            getDocDetail($(this).attr('docId'));
        });
        _docTable = $('#docListTab').DataTable();
        if (_curDoc) getDocDetail(_curDoc);
    }

    function getAllDocIds(){
        renderSearching();
        qbb.inf.getDocList(function (docs){
            docs = extractResultsFromResultsDict(docs)
            searchingFinish('Found ' + docs.length + ' documents');
            renderDocTable(docs);
        }, _passphrase);
    }

    function processDocDetails(ss){
        $('.docContent').html(highlight(ss["anns"], ss["content"], false))
        $('mark').mouseover(function (){
            $('.ann').hide();
            $(this).find('.ann').each(function (){
                let ppos = $(this).parent().position();
                $(this).css("left", ppos.left);
                $(this).css("top", ppos.top - 36);
                $(this).show();
            });

        });
        $('mark').mouseout(function (){
            $(this).find('.ann').hide();
        })

        showByLegend();
    }

    function processDocDetails_simplified(ss){
        var s = "<h2>" + ss["anns"]["SOPInstanceUID"] + "</h2>";
        s += "Total annotations:" + ss["anns"]["annotations"].length+ ", ";
        s += "Total sentences:" + ss["anns"]["sentences"].length + "<br>";
        var ann2freq = {}
        for(var i=0;i<ss["anns"]["annotations"].length;i++){
            var sty = ss["anns"]["annotations"][i]["sty"];
            if (sty in ann2freq){
                ann2freq[sty] += 1;
            }else{
                ann2freq[sty] = 1;
            }
        }
        for (var sty in ann2freq){
            s += "<li>[" + sty + "] has " + ann2freq[sty] + " annotations</li>";
        }
        $('.docContent').html(s);
    }

    function loading(docId){
        $('a.selected').removeClass('selected');
        if (docId)
            $('.docContent').html('loading ' + docId + '...')
        else {
            $('.docContent').html('');
            if (_docTable)
                _docTable.clear().draw();
        }
    }

    function getDocDetail(docId){
        loading(docId);
        _curDoc = docId;
        $('#' + _curDoc.replaceAll(".", "_")).addClass('selected');
        if (_curMapping === null)
            qbb.inf.getDocDetail(_curDoc, function (ss){
                // processDocDetails(ss);
                processDocDetails_simplified(ss);
            }, _passphrase);
        else
            qbb.inf.getDocDetailMapping(_curDoc, _curMapping, function (ss){
                // processDocDetails(ss);
                processDocDetails_simplified(ss);
            }, _passphrase);
    }

    function formatAnnotation(ann, index){
        return {
            "index": index,
            "term": "",
            "s": ann['start'],
            "e": ann['end'],
            "t": ann.sty,
            "label": ann.pref,
            "negation": isNegation(ann),
            "experiencer": isOther(ann ),
            "temporality": ann.temporality,
            "hypothetical": isHypothetical(ann),
            "abbrev": isAbbrev(ann),
            "category": "umls"
        }
    }

    function isAbbrev(ann){
        if (!ann['ruled_by'])
            return "";
        if (ann.ruled_by.includes("s_abbr.json")){
            return "abbrev";
        }else
            return "";
    }

    function isNegation(ann){
        if (!ann['ruled_by'])
            return "";
        if (ann.ruled_by.includes("positive_filters.json"))
            return "Affirmed";
        if (ann.negation === "Negated" || ann.ruled_by.includes("negation_filters.json"))
            return "Negated";
        else
            return "Affirmed";
    }

    function isOther(ann){
        if (!ann['ruled_by'])
            return "";
        if (ann.experiencer !== "Patient" || ann.ruled_by.includes("other_experiencer_filters.json"))
            return "Other";
        else
            return "";
    }

    function isHypothetical(ann){
        if (!ann['ruled_by'])
            return "";
        if (ann.temporality === "hypothetical" || ann.ruled_by.includes("hypothetical_filters.json"))
            return "hypo";
        else
            return "";
    }

    function formatPhenotypeAnn(ann, index){
        return {
            "index": index,
            "term": "",
            "s": ann['start'],
            "e": ann['end'],
            "t": ann.minor_type,
            "label": ann.str,
            "negation": isNegation(ann),
            "experiencer": ann.experiencer,
            "temporality": ann.temporality,
            "hypothetical": isHypothetical(ann),
            "abbrev": isAbbrev(ann),
            "category": "customised"
        }
    }

    /**
     * sort and filter out overlapped annotations (keep the max length annotations)
     * @param anns
     * @returns {[]} return the sorted and deduplicated annotations
     */
    function sortAndFilterAnnotations(anns){
        let sorted_anns = anns.sort(function(a, b){
            return a["s"] - b["s"];
        });
        let overlaps = [];
        for(let i=0;i<sorted_anns.length;i++){
            let a = sorted_anns[i];
            let overlap = [];
            for(let j=i+1;j<sorted_anns.length;j++){
                let b = sorted_anns[j];
                if (a.e > b.s){
                    if (overlap.length === 0)
                        overlap.push(a);
                    overlap.push(b);
                }else
                    break;
            }
            if (overlap.length > 0)
                overlaps.push(overlap);
        }
        let anns2remove = [];
        for(let i=0;i<overlaps.length;i++){
            let sortedOverlap = overlaps[i].sort(function (a, b){
                return parseInt(a.e) - parseInt(a.s) - parseInt(b.e) + parseInt(b.s);
            });
            for(let j=0; j< sortedOverlap.length - 1;j++){
                anns2remove.push(sortedOverlap[j].index);
            }
        }

        console.log("annotations to remove: ", anns2remove);
        let newAnns = [];
        for(let i=0;i<anns.length;i++){
            if (!(anns2remove.includes(anns[i].index)))
                newAnns.push(anns[i]);
        }
        console.log("removed: ", anns.length - newAnns.length);
        return newAnns;
    }

    function highlight(ann_ret, text, snippet) {
        let idx;
        let hos = [];
        let anns = ann_ret['annotations'];
        console.log(ann_ret);
        for (idx in ann_ret['annotations']){
            hos.push(formatAnnotation(anns[idx], hos.length));
        }
        for (idx in ann_ret['phenotypes']){
            hos.push(formatPhenotypeAnn(ann_ret['phenotypes'][idx], hos.length));
        }
        hos = sortAndFilterAnnotations(hos);

        const moreTextLen = 20;
        let new_str = "";
        if (hos.length > 0){
            let prev_pos = snippet ? (hos[0]['s'] > moreTextLen ? hos[0]['s'] - moreTextLen : hos[0]['s']) : 0;
            if (prev_pos > 0)
                new_str += "...";
            for (let idx in hos){
                const ann = hos[idx];
                const cls = ['default', ann.category, ann.negation, ann.temporality,
                    ann.hypothetical, ann.abbrev, ann.experiencer].join(" ");

                new_str += text.substring(prev_pos, ann["s"]) +
                    "<mark class='" + cls + "'><span title='" +
                    ann["t"] + "' class=\"ann\">" + ann["label"] + " | " +
                    ann["t"] + "</span>" + text.substring(ann["s"], ann["e"]) + "</mark>";
                prev_pos = ann["e"];
                if (snippet)
                    break;
            }
            const endPos = snippet ? Math.min(parseInt(prev_pos) + moreTextLen, text.length) : text.length;
            new_str += text.substring(prev_pos, endPos);
            if (endPos < text.length)
                new_str += "...";
        }else{
            new_str = snippet ? text.substring(0, Math.min(text.length, moreTextLen)) + "...": text;
        }
        return new_str;
    }

    function toggleAnn(){
        $('.legend mark').click(function (){
            if ($(this).hasClass("selected")){
                $(this).removeClass("selected");
                // $('.docContent .' + $(this).attr('class')).addClass("clear");
            }else{
                // $('.docContent .' + $(this).attr('class')).removeClass("clear");
                $(this).addClass("selected");
            }
            showByLegend();
        });
    }

    function showByLegend(){
        $('.legend mark').each(function (){
            const cls = $(this).attr('class').replaceAll("selected", "");
            if ($(this).hasClass("selected")){
                $('.docContent .' +  cls).removeClass("clear");
            }else{
                $('.docContent .' + cls).addClass("clear");
            }
        });
    }

    function renderSearching(){
        loading();
        var d = new Date();
        var n = d.toLocaleTimeString();
        $('.message').html('Search started at '+n+' ...');
        $('.main').hide();
    }

    function searchingFinish(msg){
        $('.message').html(msg);
        $('.main').show();
    }


    /* A generic function which can save any 'text' to a file called 'filename'
     * by popping up a Save As dialog.
     */
    function createDownload(filename, text) {
        /* Create a fake URI for 'text' and initiate a download then delete it after */
        var element = document.createElement('a');
        element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
        element.setAttribute('download', filename);
        element.style.display = 'none';
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
    }


    /* This function is called by the click() onclick button handler
     * to save the list of document ids to a CSV file
     */
    function downloadResults(docs) {
        if (docs)
            output = docs;
        else if (window.result_docs)
            output = window.result_docs;
        else
            alert('Nothing to download yet.');
        createDownload('SOPInstanceUIDs.csv', 'SOPInstanceUID\n'+output.map(it => ''+it+'\n').join(''));
    }


    /* This function takes the result of an API call { "success": True, "results": [...] }
     * and returns just the content of the results key.
     */
    function extractResultsFromResultsDict(ss) {
        if ('results' in ss) { return(ss['results']); }
        return(ss);
    }


    /* This function is called when the form is submitted,
       the submit button is pressed or Enter typed in search box.
     */
    function submitForm() {
        renderSearching();
        const query_text = $('#klsearch').val();
        const negation = $('#negationOption').val();
        const experiencer = $('#experiencerOption').val();
        const temporality = $('#temporalityOption').val();
        const sty = $('#semanticTypeOption').val();
        const test1 = $('#test1').val();
        const moda = $('#modalityOption').val();
        const start_date = $('#start_date').val();
        const end_date = $('#end_date').val();
        const returnFields = $('#returnFields').val();
        console.log('Submitted query text is:' + query_text);
        // Construct a query object from the form
        queryDict = {
            terms: [
                {
                    q: query_text,
                    negation: negation,
                    experiencer: experiencer,
                    temporality: temporality,
                    semantictype: sty
                }
            ],
            filter: {
                modalities: [ moda ], // we only pass a single modality in this array
                start_date: start_date,
                end_date: end_date
            },
            returnFields: returnFields
        };
        console.log(queryDict);
        // Send query
        if(query_text.length > 0){
            const query_type = $('input[name=searchType]:checked').val();
            if (query_type === "docs")
                qbb.inf.searchDocs(query_text, function (ss){
                    searchingFinish('Found ' + ss.length + ' results');
                    renderDocTable(ss);
                    window.result_docs=ss; // keep in global for CSV export
                }, _passphrase);
            else{
                if (_curMapping){
                    qbb.inf.searchAnnsMapping(query_text, _curMapping, function (ss){
                        ss = extractResultsFromResultsDict(ss)
                        searchingFinish('Found ' + ss.length + ' results');
                        renderDocTable(ss);
                        window.result_docs=ss; // keep in global for CSV export
                    }, _passphrase);
                }else
                    qbb.inf.searchAnns2(query_text, function (ss){
                        ss = extractResultsFromResultsDict(ss)
                        searchingFinish('Found ' + ss.length + ' results');
                        renderDocTable(ss);
                        window.result_docs=ss; // keep in global for CSV export
                    }, _passphrase, queryDict);
            }
        }else{
            getAllDocIds();
        }
    }


    /* Upload multiple CSV files and merge all into an array in csvDataStore.
     * The store is an array like [ {"Series":"123"}, {"Series":"234"}, etc ].
     *   filelist is event.target.files from onchange event,
     *   destElem is like '#idOfElement'
     */
    function csvDataStore(moreData)
    {
        if (typeof csvDataStore.staticData === 'undefined') { csvDataStore.staticData = []; }
        if (typeof moreData !== 'undefined') { csvDataStore.staticData = csvDataStore.staticData.concat(moreData); }
        return csvDataStore.staticData;
    }

    function uploadFile(filelist, destElem)
    {
        for (let ii = 0; ii < filelist.length; ii++) {
            file = filelist[ii];
            var reader = new FileReader();
            // Closure called when readAsText completes
            reader.onload = (function(theFile) {
                return function(e) {
                    csvObjects = $.csv.toObjects(e.target.result);
                    csvDataStore(csvObjects);
                }
            })(file);
            // Read in the csv file as a data URL and call onload()
            reader.readAsText(file);
        };
    }


    /* main */
    $(document).ready(function(){
        checkPassphraseNecessary();
        /* Change UI to a datepicker */
        $( function() { $( "#start_date" ).datepicker( {dateFormat:"yy-mm-dd"} ); } );
        $( function() { $( "#end_date" ).datepicker( {dateFormat:"yy-mm-dd"} ); } );
        /* Call function when Download Results button is clicked */
        /* XXX requires that global variable holds result_docs */
        $("#downloadResultsButton").click( function() { downloadResults(window.result_docs); } );
        /* When a file upload button is used */
        $("#csvFiles").change( function(e) { uploadFile(e.target.files, '#csvFileContent'); } );
        /* When user presses Enter in the search box: */
        $('#klsearch').keydown(function(event){
            if (event.which === 13 ){
                submitForm();
            }
        });
        /* When the user clicks Search button */
        $('#submitFormButton').click( function(event) { submitForm(); } );
    })

})(this.jQuery)
