// Import UI: shipment parsing runs in the Python backend.
let importerTimer, importVersion=0;
function queueImport(el){
  state.importText=el.value;
  const version=++importVersion;
  clearTimeout(importerTimer);
  importerTimer=setTimeout(async()=>{
    if(page!=='cargo')return;
    const start=el.selectionStart,end=el.selectionEnd;
    let result;
    try{result=state.importText.trim()?await api('/api/shipments/import','POST',{text:state.importText}):{patch:{},found:[],warnings:[]}}catch(e){if(version===importVersion&&page==='cargo'){state.importStatus=e.message;const status=$('#import-status');if(status)status.textContent=e.message}return}
    if(version!==importVersion||page!=='cargo')return;
    Object.assign(state,result.patch);
    state.importStatus=state.importText.trim()?(result.found.length?`Auto-filled ${result.found.join(', ')}. Review the fields before continuing. ${result.warnings.join(' ')}`:'No shipment details recognized. Use labels such as Pickup Address:, Destination:, Pieces:, Gross Weight:, and Dimensions:.'):'';
    render();
    const input=$('#shipment-importer');input.focus();input.setSelectionRange(start,end);
  },350);
}
function importer(){return `<h3><label for="shipment-importer">SHIPMENT IMPORTER</label></h3><textarea id="shipment-importer" aria-describedby="import-status" oninput="queueImport(this)" spellcheck="false">${safe(state.importText||'')}</textarea><p id="import-status" role="status" class="small-text">${safe(state.importStatus||'')}</p>`}


