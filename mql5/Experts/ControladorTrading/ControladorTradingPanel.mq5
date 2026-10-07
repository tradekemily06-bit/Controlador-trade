#property strict
#property version   "2.0"
#property description "Controlador Trading - interface nativa do ecossistema no grafico MT5."
#property description "Camada visual e operacional ligada ao runtime; DEMO por padrao."

input string InpRuntimeUrl = "http://127.0.0.1:8000";
input int    InpRefreshSeconds = 3;
input int    InpPanelWidth = 430;
input int    InpPanelHeight = 620;

string P="CTP_";
string last_cycle_id="";
string last_external_id="";
string active_view="COCKPIT";
bool runtime_ok=false;
bool watermark_enabled=true;

string Obj(string suffix){ return P+suffix; }
string WatermarkKey(){ return P+IntegerToString(ChartID())+"_WATERMARK"; }

void SetLabel(string name,string text,int x,int y,int size=10,color clr=clrWhite){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,size);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetString(0,name,OBJPROP_FONT,"Arial");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void SetButton(string name,string text,int x,int y,int w,int h){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,C'35,43,58');
   ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,C'65,78,100');
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void SetEdit(string name,string text,int x,int y,int w,int h){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_EDIT,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,C'10,14,21');
   ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,C'55,65,85');
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_READONLY,false);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void ApplyWatermark(){
   string name=Obj("WATERMARK");
   if(!watermark_enabled){
      if(ObjectFind(0,name)>=0) ObjectDelete(0,name);
      return;
   }
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   int w=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int h=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,MathMax(180,w/2));
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,MathMax(120,h/2));
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,30);
   ObjectSetInteger(0,name,OBJPROP_COLOR,C'55,65,85');
   ObjectSetString(0,name,OBJPROP_FONT,"Arial");
   ObjectSetString(0,name,OBJPROP_TEXT,"CONTROLADOR TRADING");
   ObjectSetInteger(0,name,OBJPROP_BACK,true);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void RefreshWatermarkControl(){
   SetButton(Obj("WM"),watermark_enabled?"MARCA: ATIVADA":"MARCA: DESATIVADA",20,555,172,28);
   ApplyWatermark();
}
void ToggleWatermark(){
   watermark_enabled=!watermark_enabled;
   GlobalVariableSet(WatermarkKey(),watermark_enabled?1.0:0.0);
   RefreshWatermarkControl();
   SetLabel(Obj("INFO1"),watermark_enabled?"Marca d'agua ativada no grafico.":"Marca d'agua desativada no grafico.",20,361,9,watermark_enabled?C'88,214,141':C'145,160,180');
   ChartRedraw();
}
void LoadWatermark(){
   if(GlobalVariableCheck(WatermarkKey()))
      watermark_enabled=(GlobalVariableGet(WatermarkKey())>0.5);
   RefreshWatermarkControl();
}
void Panel(){
   string bg=Obj("BG");
   if(ObjectFind(0,bg)<0) ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,8);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,18);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,InpPanelWidth);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,InpPanelHeight);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,C'9,13,20');
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,C'55,65,85');
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_HIDDEN,true);

   SetLabel(Obj("TITLE"),"CONTROLADOR TRADING",20,27,13,clrWhite);
   SetLabel(Obj("SUB"),"ECOSSISTEMA • MT5 • RUNTIME REAL",20,47,9,C'150,165,185');
   SetButton(Obj("V1"),"COCKPIT",18,67,54,25);
   SetButton(Obj("V2"),"ANALISE",74,67,54,25);
   SetButton(Obj("V3"),"MEMORIA",130,67,54,25);
   SetButton(Obj("V4"),"LAB",186,67,48,25);
   SetButton(Obj("V5"),"ENSINO",236,67,54,25);
   SetButton(Obj("V6"),"NOTIF",292,67,54,25);
   SetButton(Obj("V7"),"CONFIG",348,67,54,25);

   SetLabel(Obj("RUNTIME"),"Runtime: verificando...",20,104,10,C'255,209,102');
   SetLabel(Obj("MODE"),"Modo: DEMO / SIMULACAO",20,124,10,C'88,214,141');
   SetLabel(Obj("SIGNAL"),"AGUARDAR",20,154,22,C'255,209,102');
   SetLabel(Obj("SCORE"),"Score: —/100",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),"Aguardando analise.",20,204,9,C'180,190,205');

   SetLabel(Obj("SYML"),"ATIVO",20,236,8,C'130,145,165');
   SetEdit(Obj("SYM"),_Symbol,20,249,150,25);
   SetLabel(Obj("TFL"),"TIMEFRAME",184,236,8,C'130,145,165');
   SetEdit(Obj("TF"),EnumToString((ENUM_TIMEFRAMES)_Period),184,249,195,25);

   SetButton(Obj("ANALYZE"),"ANALISAR NO RUNTIME",20,284,172,30);
   SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
   SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
   SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);

   SetLabel(Obj("INFO1"),"Decisao: —",20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Risk Gate: verificando...",20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Memoria: verificando...",20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Estatisticas: verificando...",20,421,9,C'205,215,230');
   SetLabel(Obj("INFO5"),"Noticias: verificando...",20,441,9,C'205,215,230');

   SetLabel(Obj("CYCLEID"),"Ciclo: —",20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: —",20,483,8,C'145,160,180');
   SetLabel(Obj("PRICE"),"Preco atual: —",20,501,9,C'190,200,215');
   SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • barreiras mantidas",20,520,8,C'255,155,155');
   SetButton(Obj("WM"),"MARCA: ATIVADA",20,555,172,28);
}
void DeletePanel(){
   int total=ObjectsTotal(0,-1,-1);
   for(int i=total-1;i>=0;i--){
      string n=ObjectName(0,i,-1,-1);
      if(StringFind(n,P)==0) ObjectDelete(0,n);
   }
}
string JsonValue(string json,string key){
   string needle="\"" + key + "\":";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   while(p<StringLen(json) && (StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\n' || StringGetCharacter(json,p)=='\r')) p++;
   if(p<StringLen(json) && StringGetCharacter(json,p)=='"'){
      int q=p+1;
      while(q<StringLen(json)){
         if(StringGetCharacter(json,q)=='"' && (q==p+1 || StringGetCharacter(json,q-1)!='\\')) break;
         q++;
      }
      return StringSubstr(json,p+1,q-p-1);
   }
   int q=p;
   while(q<StringLen(json)){
      ushort c=StringGetCharacter(json,q);
      if(c==',' || c=='}' || c==']' || c=='\n' || c=='\r') break;
      q++;
   }
   return StringSubstr(json,p,q-p);
}
bool Http(string method,string path,string body,string &response,int &code){
   char data[];
   char result[];
   string headers="";
   if(body!=""){
      string h="Content-Type: application/json\r\n";
      StringToCharArray(body,data,0,StringLen(body),CP_UTF8);
      code=WebRequest(method,InpRuntimeUrl+path,h,5000,data,result,headers);
   }else{
      char empty[];
      code=WebRequest(method,InpRuntimeUrl+path,"","",5000,empty,result,headers);
   }
   response=CharArrayToString(result,0,-1,CP_UTF8);
   return code>=200 && code<300;
}
string JsonEscape(string s){
   StringReplace(s,"\\","\\\\");
   StringReplace(s,"\"","\\\"");
   return s;
}
void RefreshPreferences(){
   string r; int code=0;
   if(!Http("GET","/api/preferences","",r,code)){
      SetLabel(Obj("INFO1"),"Configuracoes: runtime indisponivel • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
      return;
   }
   string mode=JsonValue(r,"selected_mode");
   string sym=JsonValue(r,"default_symbol");
   string tf=JsonValue(r,"default_timeframe");
   string closed=JsonValue(r,"require_closed_candle");
   string filters=JsonValue(r,"require_filters");
   SetLabel(Obj("INFO1"),"Modo: "+(mode==""?"DEMO":mode)+" • simbolo: "+(sym==""?"—":sym),20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Timeframe: "+(tf==""?"—":tf)+" • candle fechado: "+(closed==""?"—":closed),20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Filtros obrigatorios: "+(filters==""?"—":filters),20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Marca d'agua: "+(watermark_enabled?"ATIVADA":"DESATIVADA")+" • persistencia local MT5",20,421,9,watermark_enabled?C'88,214,141':C'145,160,180');
   SetLabel(Obj("INFO5"),"REAL: bloqueado • preferencias nao concedem autoridade REAL",20,441,9,C'255,155,155');
}
void RefreshNotifications(){
   string r; int code=0;
   if(Http("GET","/api/notifications","",r,code)){
      string unread=JsonValue(r,"unread");
      string total=JsonValue(r,"total");
      SetLabel(Obj("INFO1"),"Notificacoes: "+(total==""?"disponiveis":total)+" • nao lidas "+(unread==""?"—":unread),20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Eventos priorizados pelo runtime.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Sem acao automatica a partir de notificacoes.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Atualizacao: HTTP "+IntegerToString(code),20,421,9,C'88,214,141');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
   }else{
      SetLabel(Obj("INFO1"),"Notificacoes: indisponiveis • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
   }
}
void RefreshLearning(){
   string r; int code=0;
   if(Http("GET","/api/learning","",r,code)){
      string progress=JsonValue(r,"progress");
      string active=JsonValue(r,"active_module");
      SetLabel(Obj("INFO1"),"Ensino: "+(active==""?"trilha disponivel":active),20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Progresso: "+(progress==""?"—":progress),20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Aprendizado separado da autorizacao operacional.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"learning_authorizes_trading=false",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
   }else{
      SetLabel(Obj("INFO1"),"Ensino: runtime indisponivel • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
   }
}
void RenderView(){
   if(active_view=="COCKPIT"){
      SetLabel(Obj("SUB"),"COCKPIT • motor, decisao, risco, execucao",20,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Motor de decisao: runtime",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Risk Gate: atualizando...",20,381,9,C'255,209,102');
      SetLabel(Obj("INFO3"),"Memoria: atualizando...",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Estatisticas: atualizando...",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Noticias: atualizando...",20,441,9,C'205,215,230');
      SetButton(Obj("ANALYZE"),"ANALISAR NO RUNTIME",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshSecondary();
   }else if(active_view=="ANALISE"){
      SetLabel(Obj("SUB"),"ANALISE • leitura produzida pelo runtime, sem valores decorativos",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR LEITURA",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      Analyze();
      SetLabel(Obj("INFO2"),"Risk Gate: "+(runtime_ok?"consultado":"runtime offline"),20,381,9,runtime_ok?C'205,215,230':C'255,118,118');
      SetLabel(Obj("INFO3"),"Fonte da leitura: endpoint /api/analyze",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Candle fechado + filtros: exigidos pelo payload",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
   }else if(active_view=="MEMORIA"){
      SetLabel(Obj("SUB"),"MEMORIA • historico, WIN/LOSS, estatisticas e auditoria",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR MEMORIA",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"ATUALIZAR ESTAT.",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshSecondary();
      SetLabel(Obj("INFO1"),"Memoria: registros consultados no runtime",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Risk Gate: dados reais do runtime",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Historico: /api/memory",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Estatisticas: /api/statistics",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
   }else if(active_view=="LAB"){
      SetLabel(Obj("SUB"),"LAB • simulacao, replay e validacao isolados da operacao REAL",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"VALIDAR AMBIENTE",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshHealth();
      RefreshSecondary();
      SetLabel(Obj("INFO1"),"Ambiente: DEMO / SIMULACAO",20,361,9,C'88,214,141');
      SetLabel(Obj("INFO2"),"Risk Gate: somente estado informado pelo runtime",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Replay: endpoint /api/replay disponivel no runtime",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Execution Gate: bloqueado para REAL",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"Aprendizado nao autoriza trading",20,441,9,C'255,155,155');
   }else if(active_view=="ENSINO"){
      SetLabel(Obj("SUB"),"ENSINO • estudo separado da autorizacao operacional",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR ENSINO",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshLearning();
   }else if(active_view=="NOTIF"){
      SetLabel(Obj("SUB"),"NOTIFICACOES • eventos do runtime sem autoridade de execucao",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR NOTIF.",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshNotifications();
   }else if(active_view=="CONFIG"){
      SetLabel(Obj("SUB"),"CONFIG • preferencias, seguranca e marca d'agua",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"LER CONFIGURACOES",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshPreferences();
   }
   RefreshWatermarkControl();
}
void RefreshHealth(){
   string r; int code=0;
   if(!Http("GET","/api/health","",r,code)){
      runtime_ok=false;
      SetLabel(Obj("RUNTIME"),"Runtime: OFFLINE / HTTP "+IntegerToString(code),20,104,10,C'255,118,118');
      SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • runtime indisponivel",20,520,8,C'255,155,155');
      return;
   }
   runtime_ok=true;
   string mode=JsonValue(r,"mode");
   string real=JsonValue(r,"real");
   string mt5=JsonValue(r,"mt5_demo");
   string exec=JsonValue(r,"execution");
   string engine=JsonValue(r,"decision_engine");
   SetLabel(Obj("RUNTIME"),"Runtime: ONLINE • HTTP "+IntegerToString(code),20,104,10,C'88,214,141');
   SetLabel(Obj("MODE"),"Modo: "+(mode==""?"SIMULACAO":mode)+" • MT5: "+(mt5==""?"DEMO":mt5),20,124,10,C'88,214,141');
   SetLabel(Obj("SAFE"),"REAL: "+(real==""?"DESABILITADO":real)+" • Execucao: "+(exec==""?"BLOQUEADA":exec),20,520,8,C'255,155,155');
   SetLabel(Obj("INFO1"),"Motor de decisao: "+(engine==""?"ONLINE":engine),20,361,9,C'205,215,230');
}
void RefreshSecondary(){
   string r; int code=0;
   if(Http("GET","/api/risk","",r,code)){
      string allowed=JsonValue(r,"allowed");
      string reason=JsonValue(r,"reason");
      SetLabel(Obj("INFO2"),"Risk Gate: "+(allowed=="true"?"PERMITIDO":"BLOQUEADO")+" • "+StringSubstr(reason,0,48),20,381,9,allowed=="true"?C'88,214,141':C'255,209,102');
   }else SetLabel(Obj("INFO2"),"Risk Gate: indisponivel",20,381,9,C'255,118,118');

   if(Http("GET","/api/statistics","",r,code)){
      string total=JsonValue(r,"total");
      string rate=JsonValue(r,"win_rate");
      SetLabel(Obj("INFO4"),"Estatisticas: "+(total==""?"0":total)+" decisoes • Win rate "+(rate==""?"—":rate),20,421,9,C'205,215,230');
   }else SetLabel(Obj("INFO4"),"Estatisticas: indisponiveis",20,421,9,C'255,118,118');

   if(Http("GET","/api/news?limit=1","",r,code)){
      string live=JsonValue(r,"live");
      SetLabel(Obj("INFO5"),"Noticias: "+(live=="true"?"ONLINE":"OFFLINE")+" • sem fonte nao interfere na decisao",20,441,9,C'205,215,230');
   }else SetLabel(Obj("INFO5"),"Noticias: indisponiveis",20,441,9,C'255,118,118');

   if(Http("GET","/api/memory?limit=1","",r,code)){
      string count=JsonValue(r,"total");
      if(count=="") count=JsonValue(r,"count");
      SetLabel(Obj("INFO3"),"Memoria: runtime consultado • registros "+(count==""?"disponiveis":count),20,401,9,C'205,215,230');
   }else SetLabel(Obj("INFO3"),"Memoria: indisponivel",20,401,9,C'255,118,118');
}
void SaveConfig(){
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=EnumToString((ENUM_TIMEFRAMES)_Period);
   string body="{\"selected_mode\":\"DEMO\",\"default_symbol\":\""+JsonEscape(sym)+"\",\"default_timeframe\":\""+JsonEscape(tf)+"\",\"require_closed_candle\":true,\"require_filters\":true}";
   string r; int code=0;
   if(Http("POST","/api/preferences",body,r,code))
      SetLabel(Obj("INFO1"),"Configuracoes sincronizadas no runtime • HTTP "+IntegerToString(code),20,361,9,C'88,214,141');
   else
      SetLabel(Obj("INFO1"),"Falha ao sincronizar configuracoes • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
}
void Analyze(){
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=EnumToString((ENUM_TIMEFRAMES)_Period);
   StringReplace(tf,"PERIOD_","");
   StringToUpper(tf);
   string body="{\"score\":50,\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"confirmed\":true,\"filters_ok\":true}";
   string r; int code=0;
   if(!Http("POST","/api/analyze",body,r,code)){
      SetLabel(Obj("REASON"),"Falha na analise • HTTP "+IntegerToString(code),20,204,9,C'255,118,118');
      return;
   }
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   string score=JsonValue(r,"score");
   string reason=JsonValue(r,"reason");
   color c=signal=="COMPRA"?C'88,214,141':signal=="VENDA"?C'255,118,118':C'255,209,102';
   SetLabel(Obj("SIGNAL"),signal,20,154,22,c);
   SetLabel(Obj("SCORE"),"Score: "+(score==""?"—":score)+"/100",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Analise concluida pelo runtime.":reason,0,62),20,204,9,C'180,190,205');
   SetLabel(Obj("INFO1"),"Decisao: "+signal+" • score "+(score==""?"—":score)+" • origem runtime",20,361,9,c);
   ChartRedraw();
}
void RunCycle(){
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=EnumToString((ENUM_TIMEFRAMES)_Period);
   StringReplace(tf,"PERIOD_","");
   StringToUpper(tf);
   string body="{\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"limit\":100,\"amount\":0.01,\"duration_seconds\":60,\"confirmed\":true,\"filters_ok\":true,\"entry_conditions\":[]}";
   string r; int code=0;
   SetLabel(Obj("INFO1"),"Executando ciclo DEMO no runtime...",20,361,9,C'255,209,102');
   if(!Http("POST","/api/runtime/cycle",body,r,code)){
      SetLabel(Obj("INFO1"),"Ciclo bloqueado/falhou • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
      return;
   }
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   string score=JsonValue(r,"score");
   string reason=JsonValue(r,"reason");
   string cid=JsonValue(r,"cycle_id");
   string eid=JsonValue(r,"external_id");
   string allowed=JsonValue(r,"execution_allowed");
   color c=signal=="COMPRA"?C'88,214,141':signal=="VENDA"?C'255,118,118':C'255,209,102';
   SetLabel(Obj("SIGNAL"),signal,20,154,22,c);
   SetLabel(Obj("SCORE"),"Score: "+(score==""?"—":score)+"/100",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Ciclo concluido.":reason,0,62),20,204,9,C'180,190,205');
   last_cycle_id=cid; last_external_id=eid;
   SetLabel(Obj("CYCLEID"),"Ciclo: "+(cid==""?"—":cid),20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: "+(eid==""?"—":eid),20,483,8,C'145,160,180');
   SetLabel(Obj("INFO1"),"Ciclo DEMO: "+signal+" • autorizado="+(allowed==""?"false":allowed),20,361,9,C'88,214,141');
}
void CloseCycle(){
   if(last_cycle_id=="" || last_external_id==""){
      SetLabel(Obj("INFO1"),"Nao ha ciclo DEMO para fechar/reconciliar.",20,361,9,C'255,209,102');
      return;
   }
   string body="{\"cycle_id\":\""+JsonEscape(last_cycle_id)+"\",\"external_id\":\""+JsonEscape(last_external_id)+"\"}";
   string r; int code=0;
   if(Http("POST","/api/runtime/close",body,r,code)){
      SetLabel(Obj("INFO1"),"Fechamento DEMO + reconciliacao confirmado.",20,361,9,C'88,214,141');
      last_cycle_id=""; last_external_id="";
   }else SetLabel(Obj("INFO1"),"Fechamento falhou/bloqueado • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
}
int OnInit(){
   Panel();
   SetView("COCKPIT");
   LoadWatermark();
   EventSetTimer(MathMax(1,InpRefreshSeconds));
   RefreshHealth();
   RefreshSecondary();
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){
   EventKillTimer();
   DeletePanel();
}
void OnTimer(){
   RefreshHealth();
   if(active_view=="COCKPIT") RefreshSecondary();
   else if(active_view=="CONFIG") RefreshPreferences();
   ApplyWatermark();
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(bid>0) SetLabel(Obj("PRICE"),"Preco atual "+_Symbol+": "+DoubleToString(bid,_Digits),20,501,9,C'190,200,215');
}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   if(sparam==Obj("V1")) { active_view="COCKPIT"; RenderView(); }
   else if(sparam==Obj("V2")) { active_view="ANALISE"; RenderView(); }
   else if(sparam==Obj("V3")) { active_view="MEMORIA"; RenderView(); }
   else if(sparam==Obj("V4")) { active_view="LAB"; RenderView(); }
   else if(sparam==Obj("V5")) { active_view="ENSINO"; RenderView(); }
   else if(sparam==Obj("V6")) { active_view="NOTIF"; RenderView(); }
   else if(sparam==Obj("V7")) { active_view="CONFIG"; RenderView(); }
   else if(sparam==Obj("ANALYZE")) {
      if(active_view=="ANALISE") Analyze();
      else if(active_view=="CONFIG") RefreshPreferences();
      else if(active_view=="MEMORIA") RefreshSecondary();
      else if(active_view=="LAB") { RefreshHealth(); RefreshSecondary(); }
      else if(active_view=="ENSINO") RefreshLearning();
      else if(active_view=="NOTIF") RefreshNotifications();
      else Analyze();
   }
   else if(sparam==Obj("CYCLE")) RunCycle();
   else if(sparam==Obj("SAVE")) SaveConfig();
   else if(sparam==Obj("CLOSE")) CloseCycle();
   else if(sparam==Obj("WM")) ToggleWatermark();
}
