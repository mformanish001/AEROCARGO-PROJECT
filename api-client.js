async function api(path,method='GET',data){
 if(location.protocol==='file:')throw new Error('Start the backend with python server.py and open http://127.0.0.1:8000.');
 const res=await fetch(path,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
 const result=await res.json();if(!res.ok)throw new Error([result.error?.message,...(result.error?.details||[]).map(x=>`${x.field}: ${x.message}`)].filter(Boolean).join(' — '));return result;
}
let savingShipment=false;
async function saveRequest(){
 if(savingShipment)return;
 if(!state.terms){$('#review-error').textContent='Please accept the demo terms before continuing.';return}
 savingShipment=true;$('#review-error').textContent='Saving shipment…';
 try{
  const saved=await api('/api/shipments','POST',state);
  const result=await api(`/api/shipments/${saved.id}/quotes`);
  requestId=saved.id;quotes=result.quotes;go('quotesPage');
 }catch(e){const el=$('#review-error');if(el)el.textContent=e.message}finally{savingShipment=false}
}
