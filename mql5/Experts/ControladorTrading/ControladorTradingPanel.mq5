#property strict
#property version   "1.0"
#property description "Controlador Trading - painel nativo integrado ao grafico MT5."
#property description "Conecta ao runtime local do Controlador em DEMO."

input string InpRuntimeUrl = "http://127.0.0.1:8000";
input int    InpRefreshSeconds = 3;
input int    InpPanelWidth = 360;
input int    InpPanelHeight = 470;

string P="CTP_";
string last_cycle_id="";
string last_external_id="";
bool runtime_ok=false;

string Obj(string suffix){ return P+suffix; }

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
   
   SetLabel(Obj("TITLE"),"CONTROLADOR TRADING",20,28,13,clrWhite);
   SetLabel(Obj("SUB"),"ECOSSISTEMA • MT5 DEMO",20,48,9,C'150,165,185');
   SetLabel(Obj("RUNTIME"),"Runtime: verificando...",20,73,10,C'255,209,102');
   SetLabel(Obj("MODE"),"Modo: DEMO / SIMULACAO",20,94,10,C'88,214,141');
   SetLabel(Obj("SIGNAL"),"AGUARDAR",20,124,20,C'255,209,102');
   SetLabel(Obj("SCORE"),"Score: —/100",20,151,10,clrWhite);
   SetLabel(Obj("REASON"),"Aguardando ciclo.",20,172,9,C'180,190,205');
   
   SetLabel(Obj("SYML"),"ATIVO",20,207,8,C'130,145,165');
   SetEdit(Obj("SYM"),_Symbol,20,220,145,25);
   SetLabel(Obj("TFL"),"TIMEFRAME",180,207,8,C'130,145,165');
   SetEdit(Obj("TF"),EnumToString((ENUM_TIMEFRAMES)_Period),180,220,145,25);
   
   SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",20,258,305,30);
   SetButton(Obj("SAVE"),"SALVAR CONFIGURACOES",20,296,305,28);
   SetButton(Obj("CLOSE"),"FECHAR DEMO + RECONCILIAR",20,331,305,28);
   
   SetLabel(Obj("CYCLEID"),"Ciclo: —",20,371,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: —",20,389,8,C'145,160,180');
   SetLabel(Obj("PRICE"),"Preco atual: —",20,407,9,C'190,200,215');
   SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • confirmacao humana obrigatoria",20,429,8,C'255,155,155');
   SetLabel(Obj("MSG"),"Painel conectado ao runtime local.",20,447,8,C'145,160,180');
}

void DeletePanel(){
   int total=ObjectsTotal(0,-1,-1);
   for(int i=total-1;i>=0;i--){
      string n=ObjectName(0,i,-1,-1);
      if(StringFind(n,P)==0) ObjectDelete(0,n);
   }
}

string JsonValue(string json,string key){
   string needle="""+key+"":";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   while(p<StringLen(json) && (StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\n' || StringGetCharacter(json,p)=='\r')) p++;
   if(p<StringLen(json) && StringGetCharacter(json,p)=='"'){
      int q=p+1;
      while(q<StringLen(json)){
         if(StringGetCharacter(json,q)=='"' && StringGetCharacter(json,q-1)!='\\') break;
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
      code=WebRequest(method,InpRuntimeUrl+path,h,5000,data,ArraySize(data)-1,result,headers);
   }else{
      char empty[];
      code=WebRequest(method,InpRuntimeUrl+path,"","",5000,empty,0,result,headers);
   }
   response=CharArrayToString(result,0,-1,CP_UTF8);
   return code>=200 && code<300;
}

void RefreshHealth(){
   string r; int code=0;
   if(!Http("GET","/api/health","",r,code)){
      runtime_ok=false;
      SetLabel(Obj("RUNTIME"),"Runtime: OFFLINE / WebRequest="+IntegerToString(code),20,73,10,C'255,118,118');
      return;
   }
   runtime_ok=true;
   string mode=JsonValue(r,"mode");
   string real=JsonValue(r,"real");
   string engine=JsonValue(r,"decision_engine");
   string mt5=JsonValue(r,"mt5_demo");
   string exec=JsonValue(r,"execution");
   SetLabel(Obj("RUNTIME"),"Runtime: ONLINE • HTTP "+IntegerToString(code),20,73,10,C'88,214,141');
   SetLabel(Obj("MODE"),"Modo: "+(mode==""?"SIMULACAO":mode)+" • MT5: "+(mt5==""?"DEMO":mt5),20,94,10,C'88,214,141');
   SetLabel(Obj("SAFE"),"REAL: "+(real==""?"DESABILITADO":real)+" • Execucao: "+(exec==""?"BLOQUEADA":exec),20,429,8,C'255,155,155');
   SetLabel(Obj("MSG"),"Motor: "+(engine==""?"ONLINE":engine)+" • dados via runtime.",20,447,8,C'145,160,180');
}

string JsonEscape(string s){
   StringReplace(s,"\\","\\\\");
   StringReplace(s,""","\\"");
   return s;
}

void SaveConfig(){
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=EnumToString((ENUM_TIMEFRAMES)_Period);
   string body="{"selected_mode":"DEMO","default_symbol":""+JsonEscape(sym)+"","default_timeframe":""+JsonEscape(tf)+"","require_closed_candle":true,"require_filters":true}";
   string r; int code=0;
   if(Http("POST","/api/preferences",body,r,code))
      SetLabel(Obj("MSG"),"Configuracoes DEMO salvas no runtime • HTTP "+IntegerToString(code),20,447,8,C'88,214,141');
   else
      SetLabel(Obj("MSG"),"Falha ao salvar configuracoes • HTTP "+IntegerToString(code),20,447,8,C'255,155,155');
}

void RunCycle(){
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=EnumToString((ENUM_TIMEFRAMES)_Period);
   StringReplace(tf,"PERIOD_","");
   StringToUpper(tf);
   string body="{"symbol":""+JsonEscape(sym)+"","timeframe":""+JsonEscape(tf)+"","limit":100,"amount":0.01,"duration_seconds":60,"confirmed":true,"filters_ok":true,"entry_conditions":[]}";
   SetLabel(Obj("MSG"),"Executando ciclo DEMO no mesmo runtime...",20,447,8,C'255,209,102');
   string r; int code=0;
   if(!Http("POST","/api/runtime/cycle",body,r,code)){
      SetLabel(Obj("MSG"),"Ciclo bloqueado/falhou • HTTP "+IntegerToString(code),20,447,8,C'255,118,118');
      return;
   }
   string signal=JsonValue(r,"signal");
   string score=JsonValue(r,"score");
   string reason=JsonValue(r,"reason");
   string cid=JsonValue(r,"cycle_id");
   string eid=JsonValue(r,"external_id");
   string accepted=JsonValue(r,"execution_allowed");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   color c=clrWhite;
   if(signal=="COMPRA") c=C'88,214,141';
   else if(signal=="VENDA") c=C'255,118,118';
   else c=C'255,209,102';
   SetLabel(Obj("SIGNAL"),signal,20,124,20,c);
   SetLabel(Obj("SCORE"),"Score: "+(score==""?"—":score)+"/100",20,151,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Ciclo concluido.":reason,0,70),20,172,9,C'180,190,205');
   last_cycle_id=cid;
   last_external_id=eid;
   SetLabel(Obj("CYCLEID"),"Ciclo: "+(cid==""?"—":cid),20,371,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: "+(eid==""?"—":eid),20,389,8,C'145,160,180');
   SetLabel(Obj("MSG"),"Ciclo DEMO concluido • autorizado="+(accepted==""?"false":accepted),20,447,8,C'88,214,141');
}

void CloseCycle(){
   if(last_cycle_id=="" || last_external_id==""){
      SetLabel(Obj("MSG"),"Nao ha ciclo DEMO com execucao para fechar.",20,447,8,C'255,209,102');
      return;
   }
   string body="{"cycle_id":""+JsonEscape(last_cycle_id)+"","external_id":""+JsonEscape(last_external_id)+""}";
   string r; int code=0;
   if(Http("POST","/api/runtime/close",body,r,code)){
      SetLabel(Obj("MSG"),"Fechamento DEMO + reconciliacao confirmado.",20,447,8,C'88,214,141');
      last_cycle_id=""; last_external_id="";
   }else{
      SetLabel(Obj("MSG"),"Fechamento bloqueado/falhou • HTTP "+IntegerToString(code),20,447,8,C'255,118,118');
   }
}

int OnInit(){
   Panel();
   EventSetTimer(MathMax(1,InpRefreshSeconds));
   RefreshHealth();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason){
   EventKillTimer();
   DeletePanel();
}

void OnTimer(){
   RefreshHealth();
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(bid>0) SetLabel(Obj("PRICE"),"Preco atual "+_Symbol+": "+DoubleToString(bid,_Digits),20,407,9,C'190,200,215');
}

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   if(sparam==Obj("CYCLE")) RunCycle();
   else if(sparam==Obj("SAVE")) SaveConfig();
   else if(sparam==Obj("CLOSE")) CloseCycle();
}
