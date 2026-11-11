#property strict
#property version   "2.0"
#property description "Controlador Trading - interface nativa do ecossistema no grafico MT5."
#property description "Camada visual e operacional ligada ao runtime; DEMO por padrao."

input string InpRuntimeUrl = "http://127.0.0.1:8000";
input int    InpRefreshSeconds = 3;
input int    InpPanelWidth = 360;
input int    InpPanelHeight = 500;

string P="CTP_";
string last_cycle_id="";
string last_external_id="";
bool cycle_identity_store_valid=true;
string active_view="COCKPIT";
string active_area="COCKPIT";
string active_module="Operação";
string assistant_conversation_id="";
string assistant_answer="";
int assistant_answer_page=0;
string memory_records[];
int memory_page=0;
bool memory_loaded=false;
bool assistant_consent_armed=false;
string selected_mode="DEMO";
bool leverage_enabled=false;
bool runtime_ok=false;
bool health_ok=false;
datetime last_analysis_bar=0;
bool panel_visible=false;
int panel_x=0;
int panel_width=360;
int panel_height=440;
string compact_signal="AGUARDAR";
string compact_score="—%";
bool compact_available=false;
struct RecoveryPosition{ string cycle_id; string external_id; string state; };
RecoveryPosition recovery_items[];
int recovery_selected=0;
bool recovery_inventory_valid=false;
bool recovery_close_armed=false;
bool kill_switch_confirm_armed=false;
string recovery_message="Inventario nao consultado.";
double panel_sx=1.0;
double panel_sy=1.0;

string CycleIdentityFileName(){
   return P+"cycle-"+IntegerToString(ChartID())+".txt";
}
bool PersistCycleIdentity(){
   if(last_cycle_id=="" || last_external_id=="") return false;
   string payload=last_cycle_id+"\r\n"+last_external_id;
   int handle=FileOpen(CycleIdentityFileName(),FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE){
      cycle_identity_store_valid=false;
      Print("Controlador: falha ao abrir arquivo local de identidade do ciclo.");
      return false;
   }
   uint written=FileWriteString(handle,payload);
   FileClose(handle);
   cycle_identity_store_valid=(written==(uint)StringLen(payload));
   if(!cycle_identity_store_valid) Print("Controlador: identidade do ciclo não foi persistida integralmente.");
   return cycle_identity_store_valid;
}
void LoadCycleIdentity(){
   if(!FileIsExist(CycleIdentityFileName())) return;
   int handle=FileOpen(CycleIdentityFileName(),FILE_READ|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE){
      cycle_identity_store_valid=false;
      Print("Controlador: arquivo de identidade do ciclo existe, mas não pôde ser lido.");
      return;
   }
   string cycle_id=FileReadString(handle);
   string external_id=FileReadString(handle);
   FileClose(handle);
   if(cycle_id!="" && external_id!=""){
      last_cycle_id=cycle_id;
      last_external_id=external_id;
   }else{
      cycle_identity_store_valid=false;
      Print("Controlador: arquivo de identidade do ciclo está incompleto; novas execuções bloqueadas.");
   }
}
void ClearCycleIdentity(){
   last_cycle_id="";
   last_external_id="";
   FileDelete(CycleIdentityFileName());
   cycle_identity_store_valid=!FileIsExist(CycleIdentityFileName());
}

string Obj(string suffix){ return P+suffix; }
string PanelVisibilityKey(){ return P+IntegerToString(ChartID())+"_PANEL_VISIBLE"; }

int SX(int x){ return panel_x+(int)MathRound(x*panel_sx); }
int SY(int y){ if(y>=104) y+=34; return (int)MathRound(18+y*panel_sy); }
int SW(int w){ return MathMax(1,(int)MathRound(w*panel_sx)); }
int SH(int h){ return MathMax(1,(int)MathRound(h*panel_sy)); }
void RefreshPanelLayout(){
   int cw=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   panel_width=MathMin(InpPanelWidth,MathMax(280,(int)MathRound(cw*0.34)));
   panel_width=MathMin(panel_width,MathMax(220,cw-24));
   panel_height=MathMin(InpPanelHeight,MathMax(280,(int)MathRound(ch*0.50)));
   panel_x=MathMax(12,cw-panel_width-12);
   panel_sx=(double)panel_width/430.0;
   panel_sy=(double)panel_height/670.0;
   string bg=Obj("BG");
   if(ObjectFind(0,bg)>=0){
      ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,panel_x);
      ObjectSetInteger(0,bg,OBJPROP_XSIZE,panel_width);
      ObjectSetInteger(0,bg,OBJPROP_YSIZE,panel_height);
   }
}
void SetLabel(string name,string text,int x,int y,int size=10,color clr=clrWhite){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,SX(x));
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,SY(y));
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,MathMax(8,(int)MathRound(size*MathMin(panel_sx,panel_sy))));
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void SetButton(string name,string text,int x,int y,int w,int h){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,SX(x));
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,SY(y));
   ObjectSetInteger(0,name,OBJPROP_XSIZE,SW(w));
   ObjectSetInteger(0,name,OBJPROP_YSIZE,SH(h));
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,MathMax(8,(int)MathRound(9*MathMin(panel_sx,panel_sy))));
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,C'35,43,58');
   ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,C'65,78,100');
   ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI Symbol");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void SetEdit(string name,string text,int x,int y,int w,int h){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_EDIT,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,SX(x));
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,SY(y));
   ObjectSetInteger(0,name,OBJPROP_XSIZE,SW(w));
   ObjectSetInteger(0,name,OBJPROP_YSIZE,SH(h));
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,MathMax(8,(int)MathRound(9*MathMin(panel_sx,panel_sy))));
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,C'10,14,21');
   ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,C'55,65,85');
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_READONLY,false);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void SetChatEdit(string name,string text,int x,int y,int w,int h){
   SetEdit(name,text,x,y,w,h);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,true);
}
void SetCompactLabel(string name,string text,int x,int y,int size,color clr,bool clickable=false){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,size);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,clickable);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
string CompactSignalText(string signal){
   if(signal=="COMPRA") return "↑ COMPRAR";
   if(signal=="VENDA") return "↓ VENDER";
   if(signal=="INDISPONIVEL" || signal=="INDISPONÍVEL") return "INDISPONÍVEL";
   return "AGUARDAR";
}
color CompactSignalColor(string signal){
   if(signal=="COMPRA") return C'88,214,141';
   if(signal=="VENDA") return C'255,118,118';
   if(signal=="INDISPONIVEL" || signal=="INDISPONÍVEL") return C'255,118,118';
   return C'255,209,102';
}
void UpdateCompactSignal(string signal,string score,bool available=true){
   compact_signal=signal;
   compact_score=(available && score!="")?DoubleToString(StringToDouble(score),0)+"%":"—%";
   compact_available=available;
   if(ObjectFind(0,Obj("COMPACT_SIGNAL"))>=0){
      ObjectSetString(0,Obj("COMPACT_SIGNAL"),OBJPROP_TEXT,available?CompactSignalText(signal):"INDISPONÍVEL");
      ObjectSetInteger(0,Obj("COMPACT_SIGNAL"),OBJPROP_COLOR,available?CompactSignalColor(signal):C'255,118,118');
   }
   if(ObjectFind(0,Obj("COMPACT_SCORE"))>=0)
      ObjectSetString(0,Obj("COMPACT_SCORE"),OBJPROP_TEXT,compact_score);
}
void RefreshPanelToggle(){
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   int cx=28;
   int cy=MathMax(42,ch-46);
   SetCompactLabel(Obj("PANEL_TOGGLE_BG"),"●",cx,cy,38,C'31,43,61',true);
   SetCompactLabel(Obj("PANEL_TOGGLE"),"C",cx,cy-1,16,clrWhite,true);
   SetCompactLabel(Obj("COMPACT_SIGNAL"),"AGUARDAR",cx+82,cy-2,13,C'255,209,102',false);
   SetCompactLabel(Obj("COMPACT_SCORE"),"—%",cx+220,cy-2,11,C'205,215,230',false);
   UpdateCompactSignal(compact_signal,compact_available?compact_score:"",compact_available);
}
void TogglePanel(){
   panel_visible=!panel_visible;
   GlobalVariableSet(PanelVisibilityKey(),panel_visible?1.0:0.0);
   if(panel_visible){ Panel(); RenderView(); Analyze(true); }
   else DeletePanel(true);
   RefreshPanelToggle();
   ChartRedraw();
}
void LoadPanelVisibility(){
   string key=PanelVisibilityKey();
   if(GlobalVariableCheck(key))
      panel_visible=(GlobalVariableGet(key)>0.5);
   else{
      panel_visible=false;
      GlobalVariableSet(key,0.0);
   }
   RefreshPanelToggle();
}

int AreaModuleCount(string area){
   if(area=="COCKPIT" || area=="ESTUDO" || area=="CENTRAL") return 6;
   if(area=="ANÁLISE") return 4;
   return 1;
}
string AreaModuleName(string area,int index){
   if(area=="COCKPIT"){
      if(index==0) return "Operação";
      if(index==1) return "Motor de Decisão";
      if(index==2) return "Gestão de Risco";
      if(index==3) return "Notificações";
      if(index==4) return "Ambiente MT5 DEMO / Simulação";
      if(index==5) return "Kill Switch";
   }else if(area=="ANÁLISE"){
      if(index==0) return "Análise de Mercado";
      if(index==1) return "Memória";
      if(index==2) return "Estatísticas";
      if(index==3) return "Relatórios";
   }else if(area=="ESTUDO"){
      if(index==0) return "Laboratório";
      if(index==1) return "Replay";
      if(index==2) return "Simulador";
      if(index==3) return "Aprendizado";
      if(index==4) return "Descobertas";
      if(index==5) return "Escola / Tutorial / Onboarding";
   }else if(area=="RESERVA FISCAL") return "Reserva Fiscal";
   else if(area=="ASSISTENTE DO ECOSSISTEMA") return "Assistente do Ecossistema";
   else if(area=="CENTRAL"){
      if(index==0) return "Financeiro";
      if(index==1) return "Configurações";
      if(index==2) return "Auditoria";
      if(index==3) return "Segurança";
      if(index==4) return "Conexões";
      if(index==5) return "Multi-Broker";
   }
   return "";
}
string AreaModuleLabel(string module){
   if(module=="Operação") return "OPER.";
   if(module=="Motor de Decisão") return "MOTOR";
   if(module=="Gestão de Risco") return "RISCO";
   if(module=="Notificações") return "ALERT.";
   if(module=="Ambiente MT5 DEMO / Simulação") return "MT5 DEMO";
   if(module=="Kill Switch") return "KILL";
   if(module=="Análise de Mercado") return "MERCADO";
   if(module=="Memória") return "MEMÓRIA";
   if(module=="Estatísticas") return "ESTAT.";
   if(module=="Relatórios") return "RELAT.";
   if(module=="Laboratório") return "LAB";
   if(module=="Replay") return "REPLAY";
      if(module=="Simulador") return "SIMULATOR";
   if(module=="Simulador") return "SIMUL.";
   if(module=="Aprendizado") return "APREND.";
   if(module=="Descobertas") return "DESCOB.";
   if(module=="Escola / Tutorial / Onboarding") return "ESCOLA";
   if(module=="Reserva Fiscal") return "RESERVA";
   if(module=="Assistente do Ecossistema") return "ASSIST.";
   if(module=="Financeiro") return "FINANC.";
   if(module=="Configurações") return "CONFIG";
   if(module=="Auditoria") return "AUDIT.";
   if(module=="Segurança") return "SEGUR.";
   if(module=="Conexões") return "CONEX.";
   if(module=="Multi-Broker") return "BROKER";
   return "—";
}
string ViewForModule(string area,string module){
   if(area=="COCKPIT"){
      if(module=="Operação") return "COCKPIT";
      if(module=="Motor de Decisão") return "DECISION";
      if(module=="Kill Switch") return "KILL_SWITCH";
      if(module=="Gestão de Risco") return "RISK";
      if(module=="Ambiente MT5 DEMO / Simulação") return "ENVIRONMENT";
      if(module=="Notificações") return "NOTIF";
   }else if(area=="ANÁLISE"){
      if(module=="Análise de Mercado") return "ANALISE";
      if(module=="Memória") return "MEMORIA";
      if(module=="Estatísticas") return "STATS";
      if(module=="Relatórios") return "REPORTS";
   }else if(area=="ESTUDO"){
      if(module=="Laboratório") return "LAB";
      if(module=="Aprendizado" || module=="Escola / Tutorial / Onboarding") return "ENSINO";
   }else if(area=="RESERVA FISCAL") return "RESERVA";
   else if(area=="ASSISTENTE DO ECOSSISTEMA") return "ASSISTENTE";
   else if(area=="CENTRAL"){
      if(module=="Financeiro") return "FINANCE";
      if(module=="Configurações") return "CONFIG";
      if(module=="Conexões") return "CONNECTIONS";
      if(module=="Segurança") return "SECURITY";
      if(module=="Auditoria") return "AUDIT";
   }
   return "UNAVAILABLE";
}
void RenderNavigation(){
   string area_labels[6]={"COCKPIT","ANÁLISE","ESTUDO","FISCAL","ASSIST.","CENTRAL"};
   for(int i=0;i<6;i++){
      string area_button=Obj("A"+IntegerToString(i+1));
      SetButton(area_button,area_labels[i],18+i*54,67,52,25);
      bool selected=(i==0 && active_area=="COCKPIT") || (i==1 && active_area=="ANÁLISE") || (i==2 && active_area=="ESTUDO") || (i==3 && active_area=="RESERVA FISCAL") || (i==4 && active_area=="ASSISTENTE DO ECOSSISTEMA") || (i==5 && active_area=="CENTRAL");
      ObjectSetInteger(0,area_button,OBJPROP_BGCOLOR,selected?C'24,86,72':C'35,43,58');
   }
   for(int i=0;i<6;i++){
      string name=AreaModuleName(active_area,i);
      string button=Obj("M"+IntegerToString(i+1));
      if(i<AreaModuleCount(active_area) && name!="")
         SetButton(button,AreaModuleLabel(name),18+i*54,98,52,25);
      if(i<AreaModuleCount(active_area) && name!="") ObjectSetInteger(0,button,OBJPROP_BGCOLOR,(name==active_module)?C'24,86,72':C'35,43,58');
      else if(ObjectFind(0,button)>=0) ObjectDelete(0,button);
   }
}
void SelectArea(string area){
   kill_switch_confirm_armed=false;
   active_area=area;
   active_module=AreaModuleName(active_area,0);
   active_view=ViewForModule(active_area,active_module);
   Panel();
   RenderView();
}
void SelectModule(int index){
   if(index<0 || index>=AreaModuleCount(active_area)) return;
   kill_switch_confirm_armed=false;
   active_module=AreaModuleName(active_area,index);
   active_view=ViewForModule(active_area,active_module);
   Panel();
   RenderView();
}

void Panel(){
   string bg=Obj("BG");
   if(ObjectFind(0,bg)<0) ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   RefreshPanelLayout();
   RefreshPanelToggle();
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,panel_x);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,18);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,panel_width);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,panel_height);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,C'9,13,20');
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,C'55,65,85');
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_HIDDEN,true);

   SetLabel(Obj("TITLE"),"Controlador Trading",20,27,13,clrWhite);
   SetLabel(Obj("SUB"),"ECOSSISTEMA • MT5 • DEMO / SIMULACAO",20,47,9,C'150,165,185');
   RenderNavigation();

   SetLabel(Obj("RUNTIME"),"Sistema: verificando...",20,104,10,C'255,209,102');
   SetLabel(Obj("MODE"),"Modo: DEMO / SIMULACAO",20,124,10,C'88,214,141');
   SetLabel(Obj("SIGNAL"),"AGUARDAR",20,154,22,C'255,209,102');
   SetLabel(Obj("SCORE"),"Qualidade: —%",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),"Aguardando analise.",20,204,9,C'180,190,205');

   SetLabel(Obj("SYML"),"ATIVO",20,236,8,C'130,145,165');
   SetEdit(Obj("SYM"),_Symbol,20,249,150,25);
   SetLabel(Obj("TFL"),"TIMEFRAME",184,236,8,C'130,145,165');
   SetEdit(Obj("TF"),NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period)),184,249,195,25);
   SetLabel(Obj("MARKET"),"Ativos/Mercados: consultando...",20,278,8,C'145,160,180');

   SetButton(Obj("ANALYZE"),"ANALISAR",20,294,172,30);
   SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,294,177,30);
   SetButton(Obj("SAVE"),"SALVAR CONFIG",20,330,172,28);
   SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,330,177,28);

   SetLabel(Obj("INFO1"),"Decisao: —",20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Risco: verificando...",20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Memoria: verificando...",20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Estatisticas: verificando...",20,421,9,C'205,215,230');
   SetLabel(Obj("INFO5"),"Noticias: verificando...",20,441,9,C'205,215,230');

   SetLabel(Obj("CYCLEID"),"Ciclo DEMO: aguardando",20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: sem atividade",20,483,8,C'145,160,180');
   SetLabel(Obj("PRICE"),"Preco atual: —",20,501,9,C'190,200,215');
   SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • barreiras mantidas",20,520,8,C'255,155,155');
   SetLabel(Obj("RECOVERY_TITLE"),"RECUPERACAO DEMO",20,545,8,C'150,165,185');
   SetLabel(Obj("RECOVERY_ITEM"),"Atualize o inventario de tickets",20,560,8,C'205,215,230');
   SetButton(Obj("REC_REFRESH"),"ATUALIZAR",20,578,82,24);
   SetButton(Obj("REC_PREV"),"<",108,578,34,24);
   SetButton(Obj("REC_NEXT"),">",148,578,34,24);
   SetButton(Obj("REC_RECONCILE"),"CONSULTAR MT5",188,578,105,24);
   SetButton(Obj("REC_CLOSE"),"FECHAR",299,578,80,24);
   SetLabel(Obj("RECOVERY_STATUS"),"Sem consulta ao broker.",20,604,8,C'145,160,180');
}
void DeletePanel(bool preserveCompact=false){
   int total=ObjectsTotal(0,-1,-1);
   for(int i=total-1;i>=0;i--){
      string n=ObjectName(0,i,-1,-1);
      if(StringFind(n,P)!=0) continue;
      if(preserveCompact && (n==Obj("PANEL_TOGGLE") || n==Obj("PANEL_TOGGLE_BG") || n==Obj("COMPACT_SIGNAL") || n==Obj("COMPACT_SCORE"))) continue;
      ObjectDelete(0,n);
   }
   if(preserveCompact) RefreshPanelToggle();
}
int JsonValueStart(string json,string key){
   string needle="\""+key+"\"";
   int p=StringFind(json,needle);
   while(p>=0){
      int q=p+StringLen(needle);
      while(q<StringLen(json) && (StringGetCharacter(json,q)==' ' || StringGetCharacter(json,q)=='\n' || StringGetCharacter(json,q)=='\r' || StringGetCharacter(json,q)=='\t')) q++;
      if(q<StringLen(json) && StringGetCharacter(json,q)==':'){
         q++;
         while(q<StringLen(json) && (StringGetCharacter(json,q)==' ' || StringGetCharacter(json,q)=='\n' || StringGetCharacter(json,q)=='\r' || StringGetCharacter(json,q)=='\t')) q++;
         return q;
      }
      p=StringFind(json,needle,p+StringLen(needle));
   }
   return -1;
}
string JsonValue(string json,string key){
   int p=JsonValueStart(json,key);
   if(p<0) return "";
   if(p<StringLen(json) && StringGetCharacter(json,p)=='"'){
      int q=p+1;
      bool escaped=false;
      for(;q<StringLen(json);q++){
         ushort c=StringGetCharacter(json,q);
         if(escaped) escaped=false;
         else if(c=='\\') escaped=true;
         else if(c=='"') break;
      }
      if(q>=StringLen(json)) return "";
      return StringSubstr(json,p+1,q-p-1);
   }
   int q=p;
   while(q<StringLen(json)){
      ushort c=StringGetCharacter(json,q);
      if(c==',' || c=='}' || c==']' || c=='\n' || c=='\r') break;
      q++;
   }
   string value=StringSubstr(json,p,q-p);
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
}
bool ExtractJsonArrayObjects(string json,string arrayKey,string &objects[]){
   ArrayResize(objects,0);
   int valueStart=JsonValueStart(json,arrayKey);
   if(valueStart<0 || valueStart>=StringLen(json) || StringGetCharacter(json,valueStart)!='[') return false;
   int length=StringLen(json),pos=valueStart+1;
   bool have_item=false,after_comma=false;
   while(pos<length){
      ushort c=StringGetCharacter(json,pos);
      if(c==' ' || c=='\n' || c=='\r' || c=='\t'){ pos++; continue; }
      if(c==']') return !after_comma;
      if(c==','){
         if(!have_item || after_comma) return false;
         after_comma=true; pos++; continue;
      }
      if(c!='{') return false;
      if(have_item && !after_comma) return false;
      int objectStart=pos,depth=0;
      bool inString=false,escaped=false;
      for(;pos<length;pos++){
         c=StringGetCharacter(json,pos);
         if(inString){
            if(escaped) escaped=false;
            else if(c=='\\') escaped=true;
            else if(c=='"') inString=false;
         }else{
            if(c=='"') inString=true;
            else if(c=='{') depth++;
            else if(c=='}'){ depth--; if(depth==0){ pos++; break; } }
         }
      }
      if(depth!=0 || inString) return false;
      int n=ArraySize(objects);
      if(ArrayResize(objects,n+1)!=n+1) return false;
      objects[n]=StringSubstr(json,objectStart,pos-objectStart);
      have_item=true; after_comma=false;
   }
   return false;
}
string JsonObjectValue(string json,string objectKey,string key){
   int valueStart=JsonValueStart(json,objectKey);
   if(valueStart<0 || valueStart>=StringLen(json) || StringGetCharacter(json,valueStart)!='{') return "";
   int depth=0;
   bool inString=false,escaped=false;
   for(int i=valueStart;i<StringLen(json);i++){
      ushort ch=StringGetCharacter(json,i);
      if(inString){
         if(escaped) escaped=false;
         else if(ch=='\\') escaped=true;
         else if(ch=='"') inString=false;
      }else{
         if(ch=='"') inString=true;
         else if(ch=='{') depth++;
         else if(ch=='}'){
            depth--;
            if(depth==0) return JsonValue(StringSubstr(json,valueStart,i-valueStart+1),key);
         }
      }
   }
   return "";
}
void RenderRecoverySelection(){
   int count=ArraySize(recovery_items);
   if(!recovery_inventory_valid){
      SetLabel(Obj("RECOVERY_ITEM"),"Inventario indisponivel ou invalido.",20,560,8,C'255,118,118');
      SetLabel(Obj("RECOVERY_STATUS"),recovery_message,20,604,8,C'255,118,118');
      return;
   }
   if(count==0){
      SetLabel(Obj("RECOVERY_ITEM"),"Nenhum ciclo pendente no ledger.",20,560,8,C'88,214,141');
      SetLabel(Obj("RECOVERY_STATUS"),"Lista vazia; consulta somente leitura.",20,604,8,C'145,160,180');
      return;
   }
   recovery_selected=MathMax(0,MathMin(recovery_selected,count-1));
   RecoveryPosition item=recovery_items[recovery_selected];
   SetLabel(Obj("RECOVERY_ITEM"),StringFormat("%d/%d Ticket %s · %s",recovery_selected+1,count,item.external_id,item.state),20,560,8,C'205,215,230');
   SetLabel(Obj("RECOVERY_STATUS"),StringSubstr(recovery_message,0,58),20,604,8,C'145,160,180');
}
bool ParseRecoveryInventory(string json){
   string objects[];
   if(!ExtractJsonArrayObjects(json,"positions",objects)) return false;
   ArrayResize(recovery_items,0);
   for(int i=0;i<ArraySize(objects);i++){
      string cycle=JsonValue(objects[i],"cycle_id");
      string ticket=JsonValue(objects[i],"external_id");
      string state=JsonValue(objects[i],"recovery_state");
      if(cycle=="" || ticket=="" || (state!="BLOCKED_ACCOUNT_IDENTITY" && state!="BROKER_CONFIRMED_OPEN" && state!="RECONCILIATION_REQUIRED")){
         ArrayResize(recovery_items,0);
         return false;
      }
      int n=ArraySize(recovery_items);
      if(ArrayResize(recovery_items,n+1)!=n+1){ ArrayResize(recovery_items,0); return false; }
      recovery_items[n].cycle_id=cycle;
      recovery_items[n].external_id=ticket;
      recovery_items[n].state=state;
   }
   return true;
}
bool RefreshRecoveryInventory(){
   string response; int code=0;
   if(!Http("GET","/api/runtime/positions/recovery/local","",response,code)){
      recovery_inventory_valid=false;
      recovery_message="Falha HTTP ao consultar inventario local.";
      RenderRecoverySelection();
      return false;
   }
   if(!ParseRecoveryInventory(response)){
      recovery_inventory_valid=false;
      recovery_message="Resposta JSON invalida; acoes bloqueadas.";
      RenderRecoverySelection();
      return false;
   }
   recovery_inventory_valid=true;
   recovery_selected=0;
   recovery_close_armed=false;
   recovery_message="Inventario lido; broker ainda nao consultado.";
   RenderRecoverySelection();
   return true;
}
void ReconcileSelectedRecovery(){
   if(!recovery_inventory_valid || ArraySize(recovery_items)==0) return;
   recovery_selected=MathMax(0,MathMin(recovery_selected,ArraySize(recovery_items)-1));
   RecoveryPosition item=recovery_items[recovery_selected];
   if(item.state=="BLOCKED_ACCOUNT_IDENTITY"){
      recovery_message="Identidade original bloqueada; sem fechamento.";
      RenderRecoverySelection();
      return;
   }
   string body="{\"cycle_id\":\""+JsonEscape(item.cycle_id)+"\",\"external_id\":\""+JsonEscape(item.external_id)+"\"}";
   string response; int code=0;
   if(!Http("POST","/api/runtime/close/local/reconcile",body,response,code)){
      recovery_message="MT5 nao confirmou; nenhuma ordem enviada.";
      RenderRecoverySelection();
      return;
   }
   string state=JsonObjectValue(response,"close_reconciliation","state");
   if(state=="CLOSED"){
      recovery_message="MT5 confirmou CLOSED; atualizando lista.";
      RefreshRecoveryInventory();
   }else if(state=="OPEN"){
      recovery_items[recovery_selected].state="BROKER_CONFIRMED_OPEN";
      recovery_close_armed=false;
      recovery_message="MT5 confirmou OPEN. Clique FECHAR e confirme novamente.";
      RenderRecoverySelection();
   }else{
      recovery_message="Estado UNKNOWN; fechamento permanece bloqueado.";
      RenderRecoverySelection();
   }
}
void CloseSelectedRecovery(){
   if(!recovery_inventory_valid || ArraySize(recovery_items)==0) return;
   recovery_selected=MathMax(0,MathMin(recovery_selected,ArraySize(recovery_items)-1));
   RecoveryPosition item=recovery_items[recovery_selected];
   if(item.state!="BROKER_CONFIRMED_OPEN"){
      recovery_message="Fechamento exige estado OPEN confirmado pelo MT5.";
      RenderRecoverySelection();
      return;
   }
   if(!recovery_close_armed){
      recovery_close_armed=true;
      recovery_message="Confirme: clique FECHAR novamente para este ticket.";
      RenderRecoverySelection();
      return;
   }
   recovery_close_armed=false;
   string body="{\"cycle_id\":\""+JsonEscape(item.cycle_id)+"\",\"external_id\":\""+JsonEscape(item.external_id)+"\"}";
   string response; int code=0;
   if(!Http("POST","/api/runtime/close/local",body,response,code)){
      recovery_message="Fechamento inconclusivo; reconciliacao necessaria.";
      RefreshRecoveryInventory();
      return;
   }
   if(JsonValue(response,"closed")=="true" && JsonValue(response,"close_state")=="CLOSED"){
      recovery_message="Fechamento confirmado pelo runtime.";
      RefreshRecoveryInventory();
      return;
   }
   recovery_message="Sem confirmacao CLOSED; consultando estado.";
   ReconcileSelectedRecovery();
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
      code=WebRequest(method,InpRuntimeUrl+path,"","",5000,empty,0,result,headers);
   }
   response=CharArrayToString(result,0,-1,CP_UTF8);
   return code>=200 && code<300;
}
string NormalizeTimeframe(string tf){
   StringTrimLeft(tf);
   StringTrimRight(tf);
   StringToUpper(tf);
   StringReplace(tf,"PERIOD_","");
   if(tf=="M1" || tf=="1M") return "1m";
   if(tf=="M5" || tf=="5M") return "5m";
   if(tf=="M15" || tf=="15M") return "15m";
   if(tf=="M30" || tf=="30M") return "30m";
   if(tf=="H1" || tf=="1H") return "1h";
   if(tf=="H4" || tf=="4H") return "4h";
   if(tf=="D1" || tf=="1D") return "1d";
   return tf;
}
string JsonEscape(string s){
   StringReplace(s,"\\","\\\\");
   StringReplace(s,"\"","\\\"");
   return s;
}
void RefreshPreferences(){
   string r; int code=0;
   if(!Http("GET","/api/preferences","",r,code)){
      SetLabel(Obj("INFO1"),"Configuracoes indisponiveis",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
      return;
   }
   string mode=JsonObjectValue(r,"preferences","selected_mode");
   string sym=JsonObjectValue(r,"preferences","default_symbol");
   string tf=JsonObjectValue(r,"preferences","default_timeframe");
   string closed=JsonObjectValue(r,"preferences","require_closed_candle");
   string filters=JsonObjectValue(r,"preferences","require_filters");
   string leverage=JsonObjectValue(r,"preferences","leverage_enabled");
   if(mode=="") mode="DEMO";
   selected_mode="DEMO";
   leverage_enabled=(leverage=="true");
   SetButton(Obj("LEVERAGE_TOGGLE"),leverage_enabled?"ALAVANCAGEM: ON":"ALAVANCAGEM: OFF",202,505,177,28);
   SetLabel(Obj("INFO1"),"Modo selecionado: "+selected_mode,20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Alavancagem: "+(leverage_enabled?"ON":"OFF"),20,381,9,leverage_enabled?C'255,209,102':C'205,215,230');
   SetLabel(Obj("INFO3"),"Candle fechado: "+(closed==""?"—":closed)+" • filtros: "+(filters==""?"—":filters),20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Simbolo: "+(sym==""?_Symbol:sym)+" • periodo: "+(tf==""?"—":tf),20,421,9,C'205,215,230');
   SetLabel(Obj("INFO5"),"REAL: BLOQUEADO • autorizacao separada",20,441,9,C'255,155,155');
}

void RefreshNotifications(){
   string r; int code=0;
   if(Http("GET","/api/notifications","",r,code)){
      string unread=JsonValue(r,"unread");
      string total=JsonValue(r,"total");
      SetLabel(Obj("INFO1"),"Notificacoes: "+(total==""?"disponiveis":total)+" • nao lidas "+(unread==""?"—":unread),20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Alertas priorizados para acompanhamento.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Sem acao automatica a partir de notificacoes.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Atualizacao concluida",20,421,9,C'88,214,141');
      SetLabel(Obj("INFO5"),"Analise operacional atualizada",20,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Notificacoes indisponiveis",20,361,9,C'255,118,118');
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
      SetLabel(Obj("INFO4"),"Estudo nao autoriza operacoes",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"Historico operacional atualizado",20,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Ensino indisponivel",20,361,9,C'255,118,118');
   }
}
string AssistantConversationFileName(){
   return P+"assistant-"+IntegerToString(ChartID())+".txt";
}
void LoadAssistantConversation(){
   if(!FileIsExist(AssistantConversationFileName())) return;
   int handle=FileOpen(AssistantConversationFileName(),FILE_READ|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE) return;
   assistant_conversation_id=FileReadString(handle);
   FileClose(handle);
}
void PersistAssistantConversation(){
   if(assistant_conversation_id=="") return;
   int handle=FileOpen(AssistantConversationFileName(),FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE) return;
   FileWriteString(handle,assistant_conversation_id);
   FileClose(handle);
}
void RefreshFiscal(){
   string r; int code=0;
   if(!Http("GET","/api/fiscal-reserve/local?limit=20","",r,code)){
      SetLabel(Obj("INFO1"),"Reserva Fiscal: runtime local indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nenhum dado fiscal foi alterado.",20,381,9,C'205,215,230');
      return;
   }
   string total=JsonValue(r,"total_reserved_brl");
   string foreign_total=JsonObjectValue(r,"foreign_pending","total");
   string domestic_total=JsonObjectValue(r,"domestic_pending","total");
   SetLabel(Obj("INFO1"),"Reserva estimada Brasil: R$ "+(total==""?"—":DoubleToString(StringToDouble(total),2)),20,361,9,C'88,214,141');
   SetLabel(Obj("INFO2"),"Pendencias Brasil: "+(domestic_total==""?"indisponivel":domestic_total)+" • fora dos totais",20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Pendencias exterior: "+(foreign_total==""?"indisponivel":foreign_total)+" • sem calculo",20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Brasil/exterior permanecem em filas separadas.",20,421,9,C'205,215,230');
   SetLabel(Obj("INFO5"),"Estimativa de planejamento; nao e imposto apurado.",20,441,9,C'255,209,102');
   SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • Reserva Fiscal somente leitura",20,520,8,C'255,155,155');
}
void RefreshAssistantStatus(){
   string r; int code=0;
   if(!Http("GET","/api/assistant/local/status","",r,code)){
      SetLabel(Obj("INFO1"),"Assistente do Ecossistema indisponivel.",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Verifique o runtime e a configuracao do provedor.",20,381,9,C'205,215,230');
      return;
   }
   string available=JsonValue(r,"available");
   SetLabel(Obj("INFO1"),available=="true"?"Assistente: provedor configurado.":"Assistente: provedor indisponivel.",20,361,9,available=="true"?C'88,214,141':C'255,118,118');
   SetLabel(Obj("INFO2"),"Chat somente leitura; consentimento exigido a cada envio.",20,381,9,C'205,215,230');
}
void RenderMemoryPage(){
   int count=ArraySize(memory_records);
   int page_size=5;
   int page_count=(count+page_size-1)/page_size;
   if(page_count<1) page_count=1;
   memory_page=MathMax(0,MathMin(memory_page,page_count-1));
   for(int row=0;row<5;row++){
      int idx=memory_page*page_size+row;
      string line=(idx<count?memory_records[idx]:"");
      SetLabel(Obj("INFO"+IntegerToString(row+1)),line,20,361+row*20,8,line==""?C'100,110,125':C'205,215,230');
   }
   SetButton(Obj("MEMORY_PREV"),"ANTERIOR",20,470,104,26);
   SetLabel(Obj("MEMORY_PAGE"),"MEMORIA "+IntegerToString(memory_page+1)+"/"+IntegerToString(page_count)+" • "+IntegerToString(count)+" REG.",138,476,8,C'150,165,185');
   SetButton(Obj("MEMORY_NEXT"),"PROXIMA",296,470,114,26);
   ObjectSetInteger(0,Obj("MEMORY_PREV"),OBJPROP_STATE,false);
   ObjectSetInteger(0,Obj("MEMORY_NEXT"),OBJPROP_STATE,false);
   ObjectSetInteger(0,Obj("MEMORY_PREV"),OBJPROP_BGCOLOR,memory_page>0?C'35,43,58':C'20,25,32');
   ObjectSetInteger(0,Obj("MEMORY_NEXT"),OBJPROP_BGCOLOR,memory_page<page_count-1?C'35,43,58':C'20,25,32');
}
void RefreshMemory(){
   string r; int code=0;
   if(!Http("GET","/api/memory?limit=50","",r,code)){
      memory_loaded=false;
      SetLabel(Obj("INFO1"),"Memoria: runtime indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Historico nao foi atualizado.",20,381,9,C'205,215,230');
      return;
   }
   string objects[];
   if(!ExtractJsonArrayObjects(r,"records",objects)){
      memory_loaded=false;
      SetLabel(Obj("INFO1"),"Memoria: resposta invalida",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Formato de historico nao reconhecido.",20,381,9,C'205,215,230');
      return;
   }
   ArrayResize(memory_records,0);
   for(int i=0;i<ArraySize(objects);i++){
      string id=JsonValue(objects[i],"decision_id");
      string created=JsonValue(objects[i],"created_at");
      string symbol=JsonValue(objects[i],"symbol");
      string timeframe=JsonValue(objects[i],"timeframe");
      string signal=JsonValue(objects[i],"signal");
      string score=JsonValue(objects[i],"score");
      string outcome=JsonValue(objects[i],"outcome");
      string confirmed=JsonValue(objects[i],"confirmed");
      if(outcome=="null") outcome="";
      if(symbol=="null") symbol="";
      if(timeframe=="null") timeframe="";
      if(score=="null") score="";
      if(id=="" || signal==""){
         ArrayResize(memory_records,0);
         memory_loaded=false;
         SetLabel(Obj("INFO1"),"Memoria: registro inconsistente",20,361,9,C'255,118,118');
         return;
      }
      string date=StringSubstr(created,0,16);
      StringReplace(date,"T"," ");
      string line=date+" "+(symbol==""?"—":symbol)+" "+(timeframe==""?"—":timeframe)+" "+signal+" "+(score==""?"—":score)+" "+(outcome==""?"ABERTA":outcome);
      if(confirmed!="true") line+=" • NAO CONFIRM.";
      int n=ArraySize(memory_records);
      if(ArrayResize(memory_records,n+1)!=n+1){ memory_loaded=false; return; }
      memory_records[n]=line;
   }
   memory_loaded=true;
   memory_page=0;
   if(ArraySize(memory_records)==0){
      for(int i=0;i<5;i++) SetLabel(Obj("INFO"+IntegerToString(i+1)),i==0?"Nenhum registro de decisao encontrado.":"",20,361+i*20,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,8,C'255,155,155');
   }else RenderMemoryPage();
}
void RefreshStatistics(){
   string r; int code=0;
   if(!Http("GET","/api/statistics","",r,code)){
      SetLabel(Obj("INFO1"),"Estatisticas: runtime indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nenhum dado foi alterado.",20,381,9,C'205,215,230');
      return;
   }
   string total=JsonValue(r,"total");
   string actionable=JsonValue(r,"actionable");
   string rate=JsonValue(r,"win_rate");
   string wins=JsonValue(r,"wins");
   string losses=JsonValue(r,"losses");
   string draws=JsonValue(r,"draws");
   string opened=JsonValue(r,"open");
   string daily=JsonObjectValue(r,"periods","daily");
   string weekly=JsonObjectValue(r,"periods","weekly");
   string monthly=JsonObjectValue(r,"periods","monthly");
   string daily_total=JsonValue(daily,"total");
   string weekly_total=JsonValue(weekly,"total");
   string monthly_total=JsonValue(monthly,"total");
   SetLabel(Obj("INFO1"),"Decisoes: "+(total==""?"nao informado":total)+" • acionaveis: "+(actionable==""?"nao informado":actionable),20,361,8,C'205,215,230');
   SetLabel(Obj("INFO2"),"Win rate: "+(rate==""?"nao informado":rate)+"% • WIN: "+(wins==""?"?":wins)+" LOSS: "+(losses==""?"?":losses),20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Empates: "+(draws==""?"nao informado":draws)+" • Abertas: "+(opened==""?"nao informado":opened),20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Hoje: "+(daily_total==""?"?":daily_total)+" • Semana: "+(weekly_total==""?"?":weekly_total)+" • Mes: "+(monthly_total==""?"?":monthly_total),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"Estatisticas historicas; nao sao garantia de resultado.",20,441,8,C'255,209,102');
}
void RefreshKillSwitchStatus(){
   string r; int code=0;
   if(!Http("GET","/api/health","",r,code)){
      SetLabel(Obj("INFO1"),"Kill Switch: estado nao confirmado",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Falha de consulta nao significa protecao inativa.",20,381,8,C'205,215,230');
      SetLabel(Obj("INFO3"),"Nenhuma acao foi executada.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Ativacao exige motivo e confirmacao.",20,421,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
      return;
   }
   string kill=JsonObjectValue(r,"operational_observability","kill_switch");
   string enabled=JsonValue(kill,"enabled");
   string state=JsonValue(kill,"state");
   string reason=JsonValue(kill,"reason");
   if(enabled=="true" || state=="ACTIVE"){
      SetLabel(Obj("INFO1"),"KILL SWITCH ATIVO • novas execucoes bloqueadas",20,361,8,C'88,214,141');
      SetLabel(Obj("INFO2"),"Motivo: "+StringSubstr(reason==""?"nao informado":reason,0,55),20,381,8,C'205,215,230');
   }else if(enabled=="false" || state=="CLEAR"){
      SetLabel(Obj("INFO1"),"Kill Switch confirmado como inativo.",20,361,9,C'255,209,102');
      SetLabel(Obj("INFO2"),"A ativacao bloqueara novas execucoes.",20,381,8,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Estado do Kill Switch nao confirmado.",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nao interprete ausencia de estado como inativo.",20,381,8,C'205,215,230');
   }
   SetLabel(Obj("INFO3"),"Confirmacao manual obrigatoria antes da ativacao.",20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Solicitacoes ja encaminhadas nao sao canceladas.",20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"Acao irreversivel nesta interface • REAL bloqueado.",20,441,7,C'255,155,155');
}
void ActivateKillSwitch(){
   if(!kill_switch_confirm_armed){
      SetLabel(Obj("INFO3"),"Confirme a ativacao antes de continuar.",20,401,8,C'255,118,118');
      return;
   }
   string reason=ObjectFind(0,Obj("KILL_REASON"))>=0?ObjectGetString(0,Obj("KILL_REASON"),OBJPROP_TEXT):"";
   StringTrimLeft(reason); StringTrimRight(reason);
   if(reason=="" || StringLen(reason)>240){
      SetLabel(Obj("INFO3"),"Informe um motivo de 1 a 240 caracteres.",20,401,8,C'255,118,118');
      return;
   }
   string body="{\"reason\":\""+JsonEscape(reason)+"\",\"confirmed\":true}";
   kill_switch_confirm_armed=false;
   SetButton(Obj("KILL_CONFIRM"),"CONFIRMAR BLOQUEIO",20,320,172,30);
   string response; int code=0;
   if(!Http("POST","/api/runtime/kill-switch/activate",body,response,code)){
      SetLabel(Obj("INFO1"),"Ativacao nao confirmada pelo runtime.",20,361,8,C'255,118,118');
      SetLabel(Obj("INFO2"),"Consulte o estado antes de repetir.",20,381,8,C'205,215,230');
      return;
   }
   string activated=JsonValue(response,"activated");
   string execution=JsonValue(response,"execution_allowed");
   kill_switch_confirm_armed=false;
   SetButton(Obj("KILL_CONFIRM"),"CONFIRMAR BLOQUEIO",20,320,172,30);
   if(activated=="true" && execution=="false"){
      SetLabel(Obj("INFO1"),"KILL SWITCH ATIVADO • novas execucoes bloqueadas",20,361,8,C'88,214,141');
      SetLabel(Obj("INFO2"),"Solicitacoes em andamento exigem reconciliacao.",20,381,8,C'255,209,102');
      SetLabel(Obj("INFO3"),"A interface nao oferece desativacao.",20,401,8,C'205,215,230');
      SetLabel(Obj("INFO4"),"Verifique pendencias no modulo de recuperacao.",20,421,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,8,C'255,155,155');
   }else{
      SetLabel(Obj("INFO1"),"Runtime nao confirmou o bloqueio.",20,361,9,C'255,118,118');
      RefreshKillSwitchStatus();
   }
}
void RefreshDecisionView(){
   string r; int code=0;
   if(!Http("GET","/api/runtime/analysis/latest","",r,code)){
      SetLabel(Obj("INFO1"),"Leitura decisao: runtime indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nenhuma decisao nova foi criada.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Ultima leitura nao confirmada.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Somente leitura.",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
      return;
   }
   string available=JsonValue(r,"available");
   string signal=JsonObjectValue(r,"analysis","signal");
   if(signal=="") signal=JsonObjectValue(r,"analysis","decision");
   string quality=JsonObjectValue(r,"analysis","quality");
   string score=JsonValue(quality,"score");
   string reason=JsonObjectValue(r,"analysis","reason");
   string symbol=JsonObjectValue(r,"analysis","symbol");
   string timeframe=JsonObjectValue(r,"analysis","timeframe");
   if(available!="true"){
      SetLabel(Obj("INFO1"),"Motor: nenhuma analise disponivel",20,361,9,C'255,209,102');
      SetLabel(Obj("INFO2"),"Sinal: AGUARDAR",20,381,9,C'255,209,102');
      SetLabel(Obj("INFO3"),"Pontuacao: nao informada",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Ativo/periodo: nao informados",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Consulta somente leitura; REAL bloqueado.",20,441,8,C'255,155,155');
      return;
   }
   SetLabel(Obj("INFO1"),"Sinal: "+(signal==""?"AGUARDAR":signal),20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Pontuacao: "+(score==""?"nao informada":score),20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Ativo: "+(symbol==""?"nao informado":symbol)+" • periodo: "+(timeframe==""?"nao informado":timeframe),20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Motivo: "+StringSubstr(reason==""?"nao informado":reason,0,55),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"Ultima decisao consultada; nao cria ordem. REAL bloqueado.",20,441,7,C'255,155,155');
}
void RefreshRiskView(){
   string r; int code=0;
   if(!Http("GET","/api/risk","",r,code)){
      SetLabel(Obj("INFO1"),"Avaliacao de risco indisponivel.",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nenhuma permissao operacional foi concedida.",20,381,9,C'205,215,230');
      return;
   }
   string allowed=JsonValue(r,"allowed");
   string reason=JsonValue(r,"reason");
   string daily=JsonObjectValue(r,"configured_limits","daily_loss_limit");
   string operations=JsonObjectValue(r,"configured_limits","max_operations");
   string streak=JsonObjectValue(r,"configured_limits","max_consecutive_losses");
   SetLabel(Obj("INFO1"),"Avaliacao: "+(allowed=="true"?"dentro dos limites":"bloqueio ativo"),20,361,9,allowed=="true"?C'88,214,141':C'255,118,118');
   SetLabel(Obj("INFO2"),"Motivo: "+(reason==""?"nao informado":StringSubstr(reason,0,55)),20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Limite perda diaria: "+(daily==""?"nao informado":daily),20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Max operacoes: "+(operations==""?"nao informado":operations)+" • perdas seguidas: "+(streak==""?"nao informado":streak),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"Consulta informativa; nao autoriza execucao. REAL bloqueado.",20,441,8,C'255,155,155');
}
void RefreshConnections(){
   string r; int code=0;
   if(!Http("GET","/api/connections","",r,code)){
      SetLabel(Obj("INFO1"),"Conexoes: runtime indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Estado dos provedores nao confirmado.",20,381,9,C'205,215,230');
      return;
   }
   string decision=JsonValue(r,"decision_core");
   string gateway=JsonValue(r,"execution_gateway");
   string mt5=JsonValue(r,"ic_markets_mt5_demo");
   string ctrader=JsonValue(r,"cTrader");
   string saas=JsonValue(r,"saas");
   string real=JsonValue(r,"real");
   SetLabel(Obj("INFO1"),"Motor decisao: "+(decision==""?"nao informado":decision),20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Gateway: "+(gateway==""?"nao informado":gateway),20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"IC Markets MT5 DEMO: "+(mt5==""?"nao informado":mt5),20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"cTrader: "+(ctrader==""?"nao informado":ctrader)+" • SaaS: "+(saas==""?"nao informado":saas),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"REAL: "+(real==""?"estado nao informado":real),20,441,9,C'255,155,155');
}
void RefreshEnvironmentView(){
   string health; int health_code=0;
   if(!Http("GET","/api/health","",health,health_code)){
      SetLabel(Obj("INFO1"),"Ambiente: runtime indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Modo nao confirmado.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Estado MT5 DEMO nao confirmado.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Execucao permitida: NAO",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
      return;
   }
   string mode=JsonValue(health,"mode");
   string mt5=JsonValue(health,"mt5_demo");
   string execution=JsonValue(health,"execution_allowed");
   string connections; int connections_code=0;
   string decision="nao confirmado",gateway="nao confirmado";
   if(Http("GET","/api/connections","",connections,connections_code)){
      string decision_value=JsonValue(connections,"decision_core");
      string gateway_value=JsonValue(connections,"execution_gateway");
      if(decision_value!="") decision=decision_value;
      if(gateway_value!="") gateway=gateway_value;
   }
   SetLabel(Obj("INFO1"),"Modo runtime: "+(mode==""?"nao informado":mode),20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"MT5 DEMO: "+(mt5==""?"nao confirmado":mt5),20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Motor: "+decision+" • Gateway: "+gateway,20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Execucao permitida: "+(execution=="true"?"SIM":"NAO"),20,421,9,C'255,209,102');
   SetLabel(Obj("INFO5"),"REAL: BLOQUEADO • status nao substitui teste local",20,441,8,C'255,155,155');
}
void RefreshSecurityView(){
   string r; int code=0;
   if(!Http("GET","/api/health","",r,code)){
      SetLabel(Obj("INFO1"),"Seguranca: runtime indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Estado de armazenamento nao confirmado.",20,381,8,C'205,215,230');
      SetLabel(Obj("INFO3"),"Gate operacional nao confirmado.",20,401,8,C'205,215,230');
      SetLabel(Obj("INFO4"),"Identidade e isolamento nao confirmados.",20,421,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO • verifique a configuracao.",20,441,8,C'255,155,155');
      return;
   }
   string storage=JsonObjectValue(r,"production_storage","state");
   string gate=JsonObjectValue(r,"production_operation_gate","storage_state");
   string identity=JsonValue(r,"trusted_identity_provider");
   string tenant=JsonValue(r,"tenant_isolation");
   string real=JsonValue(r,"real");
   SetLabel(Obj("INFO1"),"Armazenamento: "+(storage==""?"nao confirmado":storage),20,361,8,C'205,215,230');
   SetLabel(Obj("INFO2"),"Gate operacional: "+(gate==""?"nao confirmado":gate),20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Provedor identidade: "+(identity==""?"nao configurado":identity),20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Isolamento: "+(tenant==""?"nao confirmado":tenant),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"REAL: "+(real==""?"DESABILITADO / nao informado":real)+" • somente leitura",20,441,8,C'255,155,155');
}
void RefreshFinanceOverview(){
   string r; int code=0;
   if(!Http("GET","/api/fiscal-reserve?limit=50&offset=0","",r,code)){
      SetLabel(Obj("INFO1"),"Financeiro: resumo indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nenhum saldo ou reserva foi estimado.",20,381,8,C'205,215,230');
      return;
   }
   string total=JsonValue(r,"total_reserved_brl");
   string month=JsonObjectValue(r,"periods","month");
   string month_reserve=JsonValue(month,"reserve_amount_brl");
   string realized=JsonValue(month,"realized_result_brl");
   string foreign_total=JsonObjectValue(r,"foreign_pending","total");
   string domestic_response; int domestic_code=0;
   string domestic_total="?";
   if(Http("GET","/api/fiscal-reserve/domestic-pending/summary","",domestic_response,domestic_code))
      domestic_total=JsonValue(domestic_response,"total");
   SetLabel(Obj("INFO1"),"Reserva estimada Brasil: "+(total==""?"nao informada":total)+" BRL",20,361,8,C'205,215,230');
   SetLabel(Obj("INFO2"),"Reserva estimada no mes: "+(month_reserve==""?"nao informada":month_reserve)+" BRL",20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Resultado realizado no mes: "+(realized==""?"nao informado":realized)+" BRL",20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Pendencias BR: "+(domestic_total==""?"?":domestic_total)+" • exterior: "+(foreign_total==""?"?":foreign_total),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"Visao fiscal resumida; nao representa saldo bancario ou equity. Pendencias fora dos totais.",20,441,7,C'255,209,102');
}
void RefreshReports(){
   string r; int code=0;
   if(!Http("GET","/api/reports?limit=50","",r,code)){
      SetLabel(Obj("INFO1"),"Relatorios: runtime indisponivel",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nenhum dado foi alterado.",20,381,9,C'205,215,230');
      return;
   }
   string summary=JsonObjectValue(r,"summary","total");
   string actionable=JsonObjectValue(r,"summary","actionable");
   string wins=JsonObjectValue(r,"summary","wins");
   string losses=JsonObjectValue(r,"summary","losses");
   string rate=JsonObjectValue(r,"summary","win_rate");
   string count=JsonValue(r,"record_count");
   string generated=JsonValue(r,"generated_at");
   string source=JsonValue(r,"source");
   SetLabel(Obj("INFO1"),"Registros no relatorio: "+(count==""?"?":count)+" • total: "+(summary==""?"?":summary),20,361,8,C'205,215,230');
   SetLabel(Obj("INFO2"),"Acionaveis: "+(actionable==""?"?":actionable)+" • WIN: "+(wins==""?"?":wins)+" • LOSS: "+(losses==""?"?":losses),20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Win rate historico: "+(rate==""?"?":rate)+"%",20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Gerado: "+(generated==""?"nao informado":StringSubstr(generated,0,19)),20,421,8,C'145,160,180');
   SetLabel(Obj("INFO5"),"Fonte: "+(source==""?"nao informada":source)+" • somente leitura; REAL bloqueado",20,441,8,C'255,209,102');
}
void RefreshAuditView(){
   string r; int code=0;
   if(!Http("GET","/api/security/audit?limit=50","",r,code)){
      SetLabel(Obj("INFO1"),"Auditoria: acesso indisponivel ou nao autorizado",20,361,8,C'255,118,118');
      SetLabel(Obj("INFO2"),"Acesso remoto exige identidade confiavel.",20,381,8,C'205,215,230');
      SetLabel(Obj("INFO3"),"Nenhum evento foi alterado.",20,401,8,C'205,215,230');
      return;
   }
   string objects[];
   if(!ExtractJsonArrayObjects(r,"events",objects)){
      SetLabel(Obj("INFO1"),"Auditoria: resposta invalida",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Eventos nao foram interpretados.",20,381,8,C'205,215,230');
      return;
   }
   string count=JsonValue(r,"count");
   string returned=JsonValue(r,"returned");
   string retention=JsonValue(r,"retention_limit");
   string persistence=JsonValue(r,"persistence");
   SetLabel(Obj("INFO1"),"Eventos: "+(count==""?"?":count)+" • exibidos: "+(returned==""?"?":returned)+" • limite: "+(retention==""?"?":retention),20,361,8,C'205,215,230');
   for(int i=0;i<4;i++){
      string line="";
      if(i<ArraySize(objects)){
         string method=JsonValue(objects[i],"method");
         string path=JsonValue(objects[i],"path");
         string status=JsonValue(objects[i],"status");
         string request=JsonValue(objects[i],"request_id");
         line=(method==""?"?":method)+" "+(path==""?"?":StringSubstr(path,0,24))+" "+(status==""?"?":status)+" "+(request==""?"":StringSubstr(request,0,10));
      }else if(i==0 && ArraySize(objects)==0) line="Nenhum evento no historico retido.";
      SetLabel(Obj("INFO"+IntegerToString(i+2)),line,20,381+i*20,7,C'205,215,230');
   }
   SetLabel(Obj("INFO5"),"Persistencia: "+(persistence==""?"nao informada":persistence)+" • consulta somente leitura",20,461,7,persistence=="DURABLE"?C'88,214,141':C'255,209,102');
}
void ClearCockpitFields(){
   string names[]={"SYM","TF","SYML","TFL","MARKET","SIGNAL","SCORE","REASON","MODE","RECOVERY_TITLE","RECOVERY_ITEM","REC_REFRESH","REC_PREV","REC_NEXT","REC_RECONCILE","REC_CLOSE","RECOVERY_STATUS"};
   for(int i=0;i<ArraySize(names);i++)
      if(ObjectFind(0,Obj(names[i]))>=0) ObjectDelete(0,Obj(names[i]));
}
void ClearAssistantControls(){
   string names[]={"ASSISTANT_PROMPT","ASSISTANT_INPUT","ASSISTANT_CONSENT","ASSISTANT_SEND","ASSISTANT_PREV","ASSISTANT_NEXT","ASSISTANT_PAGE","MEMORY_PREV","MEMORY_NEXT","MEMORY_PAGE"};
   for(int i=0;i<ArraySize(names);i++)
      if(ObjectFind(0,Obj(names[i]))>=0) ObjectDelete(0,Obj(names[i]));
}
void RenderFiscal(){
   ClearCockpitFields();
   SetLabel(Obj("SUB"),"RESERVA FISCAL • resumo conectado ao runtime",20,47,9,C'150,165,185');
   SetButton(Obj("ANALYZE"),"ATUALIZAR RESERVA",20,294,172,30);
   if(ObjectFind(0,Obj("CYCLE"))>=0) ObjectDelete(0,Obj("CYCLE"));
   if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
   if(ObjectFind(0,Obj("CLOSE"))>=0) ObjectDelete(0,Obj("CLOSE"));
   if(ObjectFind(0,Obj("CYCLEID"))>=0) ObjectDelete(0,Obj("CYCLEID"));
   if(ObjectFind(0,Obj("EXTID"))>=0) ObjectDelete(0,Obj("EXTID"));
   if(ObjectFind(0,Obj("PRICE"))>=0) ObjectDelete(0,Obj("PRICE"));
   SetLabel(Obj("INFO1"),"Consultando Reserva Fiscal...",20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Brasil e exterior permanecem separados.",20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Pendencias nao entram nos totais.",20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Valores de planejamento nao confirmam imposto.",20,421,9,C'205,215,230');
   SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
   RefreshFiscal();
}
void RenderAssistantAnswer(){
   int total_chars=StringLen(assistant_answer);
   int page_size=330;
   int page_count=(total_chars+page_size-1)/page_size;
   if(page_count<1) page_count=1;
   assistant_answer_page=MathMax(0,MathMin(assistant_answer_page,page_count-1));
   int offset=assistant_answer_page*page_size;
   SetLabel(Obj("INFO1"),StringSubstr(assistant_answer,offset,66),20,361,8,C'205,215,230');
   SetLabel(Obj("INFO2"),StringSubstr(assistant_answer,offset+66,66),20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),StringSubstr(assistant_answer,offset+132,66),20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),StringSubstr(assistant_answer,offset+198,66),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),StringSubstr(assistant_answer,offset+264,66),20,441,8,C'205,215,230');
   SetButton(Obj("ASSISTANT_PREV"),"ANTERIOR",20,470,104,26);
   SetLabel(Obj("ASSISTANT_PAGE"),"RESPOSTA "+IntegerToString(assistant_answer_page+1)+"/"+IntegerToString(page_count),138,476,8,C'150,165,185');
   SetButton(Obj("ASSISTANT_NEXT"),"PROXIMA",296,470,114,26);
   ObjectSetInteger(0,Obj("ASSISTANT_PREV"),OBJPROP_STATE,false);
   ObjectSetInteger(0,Obj("ASSISTANT_NEXT"),OBJPROP_STATE,false);
   ObjectSetInteger(0,Obj("ASSISTANT_PREV"),OBJPROP_BGCOLOR,assistant_answer_page>0?C'35,43,58':C'20,25,32');
   ObjectSetInteger(0,Obj("ASSISTANT_NEXT"),OBJPROP_BGCOLOR,assistant_answer_page<page_count-1?C'35,43,58':C'20,25,32');
}
void RenderAssistant(){
   ClearCockpitFields();
   SetLabel(Obj("SUB"),"ASSISTENTE DO ECOSSISTEMA • leitura e orientacao",20,47,9,C'150,165,185');
   if(ObjectFind(0,Obj("ANALYZE"))>=0) ObjectDelete(0,Obj("ANALYZE"));
   if(ObjectFind(0,Obj("CYCLE"))>=0) ObjectDelete(0,Obj("CYCLE"));
   if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
   if(ObjectFind(0,Obj("CLOSE"))>=0) ObjectDelete(0,Obj("CLOSE"));
   if(ObjectFind(0,Obj("CYCLEID"))>=0) ObjectDelete(0,Obj("CYCLEID"));
   if(ObjectFind(0,Obj("EXTID"))>=0) ObjectDelete(0,Obj("EXTID"));
   if(ObjectFind(0,Obj("PRICE"))>=0) ObjectDelete(0,Obj("PRICE"));
   SetLabel(Obj("ASSISTANT_PROMPT"),"Pergunta (ate 1000 caracteres)",20,250,8,C'150,165,185');
   SetChatEdit(Obj("ASSISTANT_INPUT"),"",20,266,390,34);
   SetButton(Obj("ASSISTANT_CONSENT"),assistant_consent_armed?"CONSENTIMENTO OPENAI: SIM":"CONSENTIMENTO OPENAI: NAO",20,307,220,28);
   SetButton(Obj("ASSISTANT_SEND"),"ENVIAR",248,307,162,28);
   if(assistant_answer==""){
      SetLabel(Obj("INFO1"),"A pergunta e o contexto filtrado serao enviados a OpenAI.",20,361,8,C'205,215,230');
      SetLabel(Obj("INFO2"),"O assistente nao executa ordens nem movimenta dinheiro.",20,381,8,C'205,215,230');
      SetLabel(Obj("INFO3"),"REAL: BLOQUEADO",20,401,8,C'255,155,155');
      SetLabel(Obj("INFO4"),"Resposta aparecera apos o envio.",20,421,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"Historico completo permanece no servidor.",20,441,8,C'145,160,180');
      RefreshAssistantStatus();
   }else{
      RenderAssistantAnswer();
   }
}
void SendAssistantMessage(){
   if(!assistant_consent_armed){
      SetLabel(Obj("INFO1"),"Ative o consentimento explicito antes de enviar.",20,361,8,C'255,209,102');
      return;
   }
   if(ObjectFind(0,Obj("ASSISTANT_INPUT"))<0) return;
   string message=ObjectGetString(0,Obj("ASSISTANT_INPUT"),OBJPROP_TEXT);
   StringTrimLeft(message);
   StringTrimRight(message);
   if(message=="" || StringLen(message)>1000){
      SetLabel(Obj("INFO1"),"Informe uma pergunta de 1 a 1000 caracteres.",20,361,8,C'255,209,102');
      return;
   }
   string conversation_json=assistant_conversation_id==""?"null":"\""+JsonEscape(assistant_conversation_id)+"\"";
   string body="{\"message\":\""+JsonEscape(message)+"\",\"conversation_id\":"+conversation_json+",\"consent_to_openai\":true}";
   assistant_consent_armed=false;
   SetButton(Obj("ASSISTANT_CONSENT"),"CONSENTIMENTO OPENAI: NAO",20,307,220,28);
   string response; int code=0;
   if(!Http("POST","/api/assistant/local/chat",body,response,code)){
      string failed_id=JsonValue(response,"conversation_id");
      if(failed_id!=""){ assistant_conversation_id=failed_id; PersistAssistantConversation(); }
      SetLabel(Obj("INFO1"),"Resposta indisponivel. Consulte o historico antes de reenviar.",20,361,8,C'255,118,118');
      SetLabel(Obj("INFO2"),"Status HTTP: "+IntegerToString(code)+" • detalhes protegidos.",20,381,8,C'205,215,230');
      return;
   }
   assistant_conversation_id=JsonValue(response,"conversation_id");
   PersistAssistantConversation();
   assistant_answer=JsonValue(response,"answer");
   if(assistant_answer=="") assistant_answer="Resposta vazia ou formato inesperado.";
   assistant_answer_page=0;
   RenderAssistantAnswer();
   ObjectSetString(0,Obj("ASSISTANT_INPUT"),OBJPROP_TEXT,"");
}
void RefreshDiscoveries(){
   string resources="", observations=""; int resources_code=0, observations_code=0;
   bool resources_ok=Http("GET","/api/learning/resources","",resources,resources_code);
   bool observations_ok=Http("GET","/api/learning/observations","",observations,observations_code);
   if(!resources_ok || !observations_ok){
      SetLabel(Obj("INFO1"),"Descobertas indisponiveis • HTTP "+IntegerToString(!resources_ok?resources_code:observations_code),20,361,8,C'255,118,118');
      SetLabel(Obj("INFO2"),"Confira runtime e identidade autorizada.",20,381,8,C'205,215,230'); return;
   }
   string resource_items[], observation_items[];
   ExtractJsonArrayObjects(resources,"resources",resource_items);
   ExtractJsonArrayObjects(observations,"observations",observation_items);
   string resource_id="", resource_title="", statement="";
   if(ArraySize(resource_items)>0){
      resource_id=JsonValue(resource_items[0],"resource_id");
      resource_title=JsonValue(resource_items[0],"title");
   }
   if(ArraySize(observation_items)>0) statement=JsonValue(observation_items[0],"statement");
   SetLabel(Obj("INFO1"),"Materiais cadastrados: "+IntegerToString(ArraySize(resource_items)),20,361,8,C'205,215,230');
   SetLabel(Obj("INFO2"),"ID disponivel: "+(resource_id==""?"consulte no Estudo":resource_id),20,381,8,C'145,160,180');
   SetLabel(Obj("INFO3"),"Observacoes: "+IntegerToString(ArraySize(observation_items))+" • "+(statement==""?"sem registro":StringSubstr(statement,0,34)),20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Registros continuam NAO VALIDADOS.",20,421,8,C'255,209,102');
   SetLabel(Obj("INFO5"),"Descobertas nao alteram sinais nem execucao.",20,441,8,C'255,155,155');
}
void SaveDiscovery(){
   string resource_id=ObjectGetString(0,Obj("DISC_RESOURCE"),OBJPROP_TEXT);
   string statement=ObjectGetString(0,Obj("DISC_STATEMENT"),OBJPROP_TEXT);
   string concepts=ObjectGetString(0,Obj("DISC_CONCEPTS"),OBJPROP_TEXT);
   string evidence=ObjectGetString(0,Obj("DISC_EVIDENCE"),OBJPROP_TEXT);
   StringTrimLeft(resource_id); StringTrimRight(resource_id);
   StringTrimLeft(statement); StringTrimRight(statement);
   if(resource_id=="" || statement=="" || StringLen(statement)>3000 || StringLen(concepts)>300 || StringLen(evidence)>1000){
      SetLabel(Obj("INFO1"),"Informe ID e observacao (ate 3000 caracteres); conceitos ate 300 e evidencia ate 1000.",20,361,8,C'255,118,118'); return;
   }
   string q=CharToString(34);
   string concept_items[]; int concept_count=StringSplit(concepts,',',concept_items);
   string concepts_json="[";
   for(int i=0;i<concept_count;i++){
      string concept=concept_items[i];
      StringTrimLeft(concept); StringTrimRight(concept);
      if(concept=="") continue;
      if(StringLen(concepts_json)>1) concepts_json+=",";
      concepts_json+=q+JsonEscape(concept)+q;
   }
   concepts_json+="]";
   string body="{"+q+"resource_id"+q+":"+q+JsonEscape(resource_id)+q+","+
      q+"statement"+q+":"+q+JsonEscape(statement)+q+","+
      q+"concepts"+q+":"+concepts_json+","+
      q+"evidence"+q+":"+(evidence==""?"null":q+JsonEscape(evidence)+q)+","+
      q+"validated"+q+":false}";
   string response=""; int code=0;
   if(!Http("POST","/api/learning/observations",body,response,code)){
      SetLabel(Obj("INFO1"),"Nao foi possivel guardar • HTTP "+IntegerToString(code),20,361,8,C'255,118,118'); return;
   }
   SetLabel(Obj("INFO1"),"Descoberta registrada como NAO VALIDADA.",20,361,8,C'88,214,141');
   SetLabel(Obj("INFO2"),"ID: "+resource_id,20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Sem efeito em sinais, filtros ou execucao.",20,401,8,C'255,155,155');
   ObjectSetString(0,Obj("DISC_STATEMENT"),OBJPROP_TEXT,"");
   ObjectSetString(0,Obj("DISC_CONCEPTS"),OBJPROP_TEXT,"");
   ObjectSetString(0,Obj("DISC_EVIDENCE"),OBJPROP_TEXT,"");
   RefreshDiscoveries();
   SetLabel(Obj("INFO1"),"Descoberta registrada como NAO VALIDADA.",20,361,8,C'88,214,141');
}
void RunHistoricalReplay(){
   string response=""; int code=0;
   string symbol=_Symbol;
   string timeframe=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   string q=CharToString(34);
   string body="{"+q+"symbol"+q+":"+q+JsonEscape(symbol)+q+","+q+"timeframe"+q+":"+q+JsonEscape(timeframe)+q+","+q+"limit"+q+":100}";
   if(!Http("POST","/api/replay/mt5",body,response,code)){
      SetLabel(Obj("INFO1"),"Replay indisponivel • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Runtime sem resposta; nenhuma ordem foi enviada.",20,381,8,C'205,215,230'); return;
   }
   string source=JsonValue(response,"source"), symbol_out=JsonValue(response,"symbol");
   string tf_out=JsonValue(response,"timeframe"), candles=JsonValue(response,"candles_replayed");
   string buys=JsonValue(response,"buy_signals"), sells=JsonValue(response,"sell_signals");
   string waiting=JsonValue(response,"waiting"), orders=JsonValue(response,"orders_sent");
   SetLabel(Obj("INFO1"),"Replay: "+(candles==""?"nao informado":candles)+" candles",20,361,9,C'88,214,141');
   SetLabel(Obj("INFO2"),"Ativo/periodo: "+(symbol_out==""?symbol:symbol_out)+" / "+(tf_out==""?timeframe:tf_out),20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Compra: "+(buys==""?"—":buys)+" • Venda: "+(sells==""?"—":sells),20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Aguardar: "+(waiting==""?"—":waiting)+" • Fonte: "+(source==""?"nao informada":source),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"Ordens enviadas: "+(orders==""?"nao confirmado":orders)+" • Execucao: NAO",20,441,8,C'255,155,155');
}
void RunHistoricalSimulator(){
   string stop_text=ObjectGetString(0,Obj("SIM_STOP"),OBJPROP_TEXT);
   string target_text=ObjectGetString(0,Obj("SIM_TARGET"),OBJPROP_TEXT);
   string quantity_text=ObjectGetString(0,Obj("SIM_QTY"),OBJPROP_TEXT);
   string multiplier_text=ObjectGetString(0,Obj("SIM_MULT"),OBJPROP_TEXT);
   string spread_text=ObjectGetString(0,Obj("SIM_SPREAD"),OBJPROP_TEXT);
   string slippage_text=ObjectGetString(0,Obj("SIM_SLIP"),OBJPROP_TEXT);
   string commission_text=ObjectGetString(0,Obj("SIM_COMM"),OBJPROP_TEXT);
   if(stop_text=="" || target_text=="" || quantity_text=="" || multiplier_text=="" || spread_text=="" || slippage_text=="" || commission_text==""){
      SetLabel(Obj("INFO1"),"Preencha todos os parametros; custo zero = digite 0.",20,361,8,C'255,209,102'); return;
   }
   double stop=StringToDouble(stop_text), target=StringToDouble(target_text);
   double quantity=StringToDouble(quantity_text), multiplier=StringToDouble(multiplier_text);
   double spread=StringToDouble(spread_text), slippage=StringToDouble(slippage_text), commission=StringToDouble(commission_text);
   if(stop<=0 || target<=0 || quantity<=0 || multiplier<=0 || spread<0 || slippage<0 || commission<0){
      SetLabel(Obj("INFO1"),"Stop, alvo, quantidade e multiplicador > 0; custos >= 0.",20,361,8,C'255,118,118'); return;
   }
   string symbol=_Symbol, timeframe=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   string q=CharToString(34);
   string body="{"+q+"symbol"+q+":"+q+JsonEscape(symbol)+q+","+q+"timeframe"+q+":"+q+JsonEscape(timeframe)+q+
      ","+q+"limit"+q+":200,"+q+"minimum_directional_score"+q+":80,"+
      q+"stop_distance"+q+":"+DoubleToString(stop,8)+","+
      q+"take_profit_distance"+q+":"+DoubleToString(target,8)+","+
      q+"quantity_units"+q+":"+DoubleToString(quantity,8)+","+
      q+"contract_multiplier"+q+":"+DoubleToString(multiplier,8)+","+
      q+"spread_price_units"+q+":"+DoubleToString(spread,8)+","+
      q+"slippage_price_units_per_side"+q+":"+DoubleToString(slippage,8)+","+
      q+"commission_quote_per_unit_round_turn"+q+":"+DoubleToString(commission,8)+"}";
   string response=""; int code=0;
   if(!Http("POST","/api/simulator/mt5/backtest",body,response,code)){
      SetLabel(Obj("INFO1"),"Backtest indisponivel • HTTP "+IntegerToString(code),20,361,8,C'255,118,118');
      SetLabel(Obj("INFO2"),"Nenhuma ordem foi enviada.",20,381,8,C'205,215,230'); return;
   }
   string trades=JsonValue(response,"trade_count"), win=JsonValue(response,"win_rate");
   string factor=JsonValue(response,"profit_factor"), pnl=JsonValue(response,"net_pnl_quote");
   string costs=JsonValue(response,"total_costs_quote"), candles=JsonValue(response,"candles_processed");
   string drawdown=JsonValue(response,"max_drawdown_quote"), losses=JsonValue(response,"max_consecutive_losses");
   SetLabel(Obj("INFO1"),"Operacoes: "+(trades==""?"?":trades)+" • Acerto: "+(win==""?"?":win)+"%",20,361,8,C'88,214,141');
   SetLabel(Obj("INFO2"),"Fator lucro: "+(factor==""?"nao informado":factor)+" • Liquido: "+(pnl==""?"?":pnl),20,381,8,C'205,215,230');
   SetLabel(Obj("INFO3"),"Custos: "+(costs==""?"?":costs)+" • Candles: "+(candles==""?"?":candles),20,401,8,C'205,215,230');
   SetLabel(Obj("INFO4"),"Drawdown: "+(drawdown==""?"?":drawdown)+" • Seq. perdas: "+(losses==""?"?":losses),20,421,8,C'205,215,230');
   SetLabel(Obj("INFO5"),"Historico hipotetico • ordens: NAO • REAL: BLOQUEADO",20,441,8,C'255,155,155');
}
void RenderView(){
   ClearAssistantControls();
   string simulator_controls[]={"SIM_STOP","SIM_TARGET","SIM_QTY","SIM_MULT","SIM_SPREAD","SIM_SLIP","SIM_COMM","SIM_RUN","SIM_L1","SIM_L2","SIM_L3","SIM_L4"};
   string discovery_controls[]={"DISC_RESOURCE","DISC_STATEMENT","DISC_CONCEPTS","DISC_EVIDENCE","DISC_SAVE","DISC_REFRESH","DISC_L1","DISC_L2","DISC_L3","DISC_L4"};
   for(int k=0;k<ArraySize(discovery_controls);k++) if(ObjectFind(0,Obj(discovery_controls[k]))>=0) ObjectDelete(0,Obj(discovery_controls[k]));
   for(int k=0;k<ArraySize(simulator_controls);k++) if(ObjectFind(0,Obj(simulator_controls[k]))>=0) ObjectDelete(0,Obj(simulator_controls[k]));
   string replay_controls[]={"REPLAY_RUN"};
   for(int k=0;k<ArraySize(replay_controls);k++) if(ObjectFind(0,Obj(replay_controls[k]))>=0) ObjectDelete(0,Obj(replay_controls[k]));
   string kill_controls[]={"KILL_REASON","KILL_CONFIRM","KILL_ACTIVATE"};
   for(int k=0;k<ArraySize(kill_controls);k++) if(ObjectFind(0,Obj(kill_controls[k]))>=0) ObjectDelete(0,Obj(kill_controls[k]));
   string action_buttons[]={"ANALYZE","CYCLE","SAVE","CLOSE"};
   for(int i=0;i<ArraySize(action_buttons);i++)
      if(ObjectFind(0,Obj(action_buttons[i]))>=0) ObjectDelete(0,Obj(action_buttons[i]));
   if(active_view=="UNAVAILABLE"){
      ClearCockpitFields();
      string stale[]={"ANALYZE","CYCLE","SAVE","CLOSE","CYCLEID","EXTID","PRICE","SAFE","RECOVERY_TITLE","RECOVERY_ITEM","REC_REFRESH","REC_PREV","REC_NEXT","REC_RECONCILE","REC_CLOSE","MODE_TOGGLE","LEVERAGE_TOGGLE","KILL_REASON","KILL_CONFIRM","KILL_ACTIVATE"};
      for(int i=0;i<ArraySize(stale);i++) if(ObjectFind(0,Obj(stale[i]))>=0) ObjectDelete(0,Obj(stale[i]));
      SetLabel(Obj("SUB"),active_area+" • "+active_module,20,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Modulo visivel; integracao operacional em desenvolvimento.",20,361,8,C'255,209,102');
      SetLabel(Obj("INFO2"),"Nenhuma acao sera simulada ou apresentada como concluida.",20,381,8,C'205,215,230');
      SetLabel(Obj("INFO3"),"Esta area sera habilitada apos integracao e validacao.",20,401,8,C'205,215,230');
      SetLabel(Obj("INFO4"),"REAL: BLOQUEADO",20,421,8,C'255,155,155');
      SetLabel(Obj("INFO5"),"Runtime compartilhado com o painel Streamlit.",20,441,8,C'145,160,180');
      return;
   }
   if(active_view=="RESERVA") { RenderFiscal(); return; }
   if(active_view=="ASSISTENTE") { RenderAssistant(); return; }
   if(active_view=="DISCOVERIES"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"DESCOBERTAS • observacoes vinculadas a materiais de estudo",20,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Informe o ID do material cadastrado no Estudo.",20,361,8,C'205,215,230');
      SetLabel(Obj("INFO2"),"A observacao sera salva como NAO VALIDADA.",20,381,8,C'255,209,102');
      SetLabel(Obj("INFO3"),"Conceitos: separados por virgula (opcional).",20,401,8,C'205,215,230');
      SetLabel(Obj("INFO4"),"Nao influencia sinais, filtros ou parametros.",20,421,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"Execucao permitida: NAO • REAL bloqueado",20,441,8,C'255,155,155');
      SetLabel(Obj("DISC_L1"),"ID do material",20,135,8,C'205,215,230');
      SetChatEdit(Obj("DISC_RESOURCE"),"",120,130,180,24);
      SetLabel(Obj("DISC_L2"),"Observacao",20,170,8,C'205,215,230');
      SetChatEdit(Obj("DISC_STATEMENT"),"",120,165,180,24);
      SetLabel(Obj("DISC_L3"),"Conceitos",20,205,8,C'205,215,230');
      SetChatEdit(Obj("DISC_CONCEPTS"),"",120,200,180,24);
      SetLabel(Obj("DISC_L4"),"Evidencia",20,240,8,C'205,215,230');
      SetChatEdit(Obj("DISC_EVIDENCE"),"",120,235,180,24);
      SetButton(Obj("DISC_SAVE"),"GUARDAR DESCOBERTA",20,275,170,28);
      SetButton(Obj("DISC_REFRESH"),"ATUALIZAR",200,275,100,28);
      RefreshDiscoveries(); return;
   }
   if(active_view=="REPLAY"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"REPLAY HISTORICO • candles fechados do grafico MT5",20,47,9,C'150,165,185');
      SetButton(Obj("REPLAY_RUN"),"REPRODUZIR 100 CANDLES",20,284,220,30);
      SetLabel(Obj("INFO1"),"Ativo e periodo seguem o grafico atual.",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"A reproducao usa somente candles historicos fechados.",20,381,8,C'205,215,230');
      SetLabel(Obj("INFO3"),"Nao cria ordens nem altera memoria operacional.",20,401,8,C'205,215,230');
      SetLabel(Obj("INFO4"),"Historico depende da disponibilidade no runtime.",20,421,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL bloqueado • execucao permitida: NAO",20,441,8,C'255,155,155'); return;
   }
   if(active_view=="SIMULATOR"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"SIMULADOR HISTORICO • backtest sem ordens",20,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Preencha todos os campos; custos zero = digite 0.",20,361,8,C'205,215,230');
      SetLabel(Obj("INFO2"),"P&L na moeda cotada; sem conversao cambial.",20,381,8,C'205,215,230');
      SetLabel(Obj("INFO3"),"Nao integra margem, swap ou Risk Manager.",20,401,8,C'255,209,102');
      SetLabel(Obj("INFO4"),"Ativo/timeframe seguem o grafico • 200 candles • score 80.",20,421,8,C'205,215,230');
      SetLabel(Obj("INFO5"),"Ordens enviadas: NAO • REAL: BLOQUEADO",20,441,8,C'255,155,155');
      SetLabel(Obj("SIM_L1"),"Stop / Alvo",20,145,8,C'205,215,230');
      SetChatEdit(Obj("SIM_STOP"),"",100,140,95,24); SetChatEdit(Obj("SIM_TARGET"),"",205,140,95,24);
      SetLabel(Obj("SIM_L2"),"Qtd / Mult.",20,180,8,C'205,215,230');
      SetChatEdit(Obj("SIM_QTY"),"",100,175,95,24); SetChatEdit(Obj("SIM_MULT"),"",205,175,95,24);
      SetLabel(Obj("SIM_L3"),"Spread / Slip",20,215,8,C'205,215,230');
      SetChatEdit(Obj("SIM_SPREAD"),"",100,210,95,24); SetChatEdit(Obj("SIM_SLIP"),"",205,210,95,24);
      SetLabel(Obj("SIM_L4"),"Comissao",20,250,8,C'205,215,230');
      SetChatEdit(Obj("SIM_COMM"),"",100,245,200,24);
      SetButton(Obj("SIM_RUN"),"EXECUTAR BACKTEST HISTORICO",20,285,280,30); return;
   }
   if(active_view=="KILL_SWITCH"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"KILL SWITCH • bloqueio protegido de novas execucoes",20,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Consultando estado do Kill Switch...",20,361,9,C'255,209,102');
      SetChatEdit(Obj("KILL_REASON"),"",20,284,340,25);
      SetButton(Obj("KILL_CONFIRM"),"CONFIRMAR BLOQUEIO",20,320,172,30);
      SetButton(Obj("KILL_ACTIVATE"),"ATIVAR KILL SWITCH",202,320,177,30);
      RefreshKillSwitchStatus();
   }else if(active_view=="DECISION"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"MOTOR DE DECISAO • ultima leitura, somente leitura",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR MOTOR",20,284,172,30);
      RefreshDecisionView();
   }else if(active_view=="COCKPIT"){
      SetLabel(Obj("SUB"),"COCKPIT • motor, decisao, risco, execucao",20,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Análise do ecossistema",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Risco: atualizando...",20,381,9,C'255,209,102');
      SetLabel(Obj("INFO3"),"Memoria: atualizando...",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Estatisticas: atualizando...",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Noticias: atualizando...",20,441,9,C'205,215,230');
      SetButton(Obj("ANALYZE"),"ANALISAR",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      SetLabel(Obj("CYCLEID"),"Ciclo DEMO: "+(last_cycle_id==""?"aguardando":"atualizado"),20,465,8,C'145,160,180');
      SetLabel(Obj("EXTID"),"Execucao: "+(last_external_id==""?"sem atividade":"registrada"),20,483,8,C'145,160,180');
      SetLabel(Obj("PRICE"),"Preco atual: —",20,501,9,C'190,200,215');
      SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • barreiras mantidas",20,520,8,C'255,155,155');
      RefreshSecondary();
   }else if(active_view=="ANALISE"){
      SetLabel(Obj("SUB"),"ANALISE • leitura atual do ecossistema",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR LEITURA",20,284,172,30);
      Analyze();
      SetLabel(Obj("INFO2"),"Risco: "+(runtime_ok?"atualizado":"sistema indisponivel"),20,381,9,runtime_ok?C'205,215,230':C'255,118,118');
      SetLabel(Obj("INFO3"),"Fonte: analise atual do ecossistema",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Candle fechado + filtros: exigidos pelo payload",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Sem acao automatica a partir de notificacoes",20,441,9,C'205,215,230');
   }else if(active_view=="RISK"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"GESTAO DE RISCO • consulta somente leitura",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR RISCO",20,284,172,30);
      RefreshRiskView();
   }else if(active_view=="STATS"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"ESTATISTICAS • historico consolidado do runtime",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR ESTAT.",20,284,172,30);
      RefreshStatistics();
   }else if(active_view=="CONNECTIONS"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"CONEXOES • estado reportado pelos provedores",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR CONEXOES",20,284,172,30);
      RefreshConnections();
   }else if(active_view=="ENVIRONMENT"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"AMBIENTE MT5 DEMO / SIMULACAO • consulta somente leitura",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR AMBIENTE",20,284,172,30);
      RefreshEnvironmentView();
   }else if(active_view=="SECURITY"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"SEGURANCA • postura reportada pelo runtime",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR SEGURANCA",20,284,172,30);
      RefreshSecurityView();
   }else if(active_view=="FINANCE"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"FINANCEIRO • visao geral fiscal; nao representa saldo bancario",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR FINANCEIRO",20,284,172,30);
      RefreshFinanceOverview();
   }else if(active_view=="REPORTS"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"RELATORIOS • resumo historico do runtime, somente leitura",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR RELATORIO",20,284,172,30);
      RefreshReports();
   }else if(active_view=="AUDIT"){
      ClearCockpitFields();
      SetLabel(Obj("SUB"),"AUDITORIA • trilha de seguranca e requisicoes",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR AUDITORIA",20,284,172,30);
      RefreshAuditView();
   }else if(active_view=="MEMORIA"){
      SetLabel(Obj("SUB"),"MEMORIA • historico de decisoes e resultados registrados",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR MEMORIA",20,284,172,30);
      RefreshMemory();
   }else if(active_view=="LAB"){
      SetLabel(Obj("SUB"),"LAB • laboratorio e validacao isolados da operacao REAL",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"VALIDAR AMBIENTE",20,284,172,30);
      RefreshHealth();
      RefreshSecondary();
      SetLabel(Obj("INFO1"),"Runtime: "+(runtime_ok?"conectado":"indisponivel")+"; DEMO nao confirmado",20,361,9,runtime_ok?C'88,214,141':C'255,118,118');
      SetLabel(Obj("INFO2"),"Risco: avaliacao atual",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Replay: abra o modulo proprio",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Protecao operacional ativa",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Aprendizado separado da operacao",20,441,9,C'205,215,230');
   }else if(active_view=="ENSINO"){
      SetLabel(Obj("SUB"),"ENSINO • estudo separado da autorizacao operacional",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR ENSINO",20,284,172,30);
      RefreshLearning();
   }else if(active_view=="NOTIF"){
      SetLabel(Obj("SUB"),"NOTIFICACOES • alertas e avisos do sistema",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR NOTIF.",20,284,172,30);
      RefreshNotifications();
   }else if(active_view=="CONFIG"){
      SetLabel(Obj("SUB"),"CONFIG • preferencias e seguranca",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR CONFIG",20,284,172,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      if(ObjectFind(0,Obj("CYCLE"))>=0) ObjectDelete(0,Obj("CYCLE"));
      if(ObjectFind(0,Obj("CLOSE"))>=0) ObjectDelete(0,Obj("CLOSE"));
      if(ObjectFind(0,Obj("CYCLEID"))>=0) ObjectDelete(0,Obj("CYCLEID"));
      if(ObjectFind(0,Obj("EXTID"))>=0) ObjectDelete(0,Obj("EXTID"));
      if(ObjectFind(0,Obj("PRICE"))>=0) ObjectDelete(0,Obj("PRICE"));
      if(ObjectFind(0,Obj("SAFE"))>=0) ObjectDelete(0,Obj("SAFE"));
      RefreshPreferences();
   }
   if(active_view!="CONFIG"){
      if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
      if(ObjectFind(0,Obj("MODE_TOGGLE"))>=0) ObjectDelete(0,Obj("MODE_TOGGLE"));
      if(ObjectFind(0,Obj("LEVERAGE_TOGGLE"))>=0) ObjectDelete(0,Obj("LEVERAGE_TOGGLE"));
   }

}
void RefreshHealth(){
   if(active_view=="UNAVAILABLE") return;
   string r; int code=0;
   if(!Http("GET","/api/health","",r,code)){
      runtime_ok=false;
      health_ok=false;
      UpdateCompactSignal("INDISPONIVEL","",false);
      SetLabel(Obj("RUNTIME"),"Sistema: indisponivel",20,104,10,C'255,118,118');
      if(active_view=="CONFIG") SetLabel(Obj("INFO5"),"REAL: BLOQUEADO • sistema indisponivel",20,441,9,C'255,155,155');
      else SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • sistema indisponivel",20,520,8,C'255,155,155');
      return;
   }
   runtime_ok=true;
   health_ok=true;
   string mode=JsonValue(r,"mode");
   string mt5=JsonValue(r,"mt5_demo");
   string engine=JsonValue(r,"decision_engine");
   SetLabel(Obj("RUNTIME"),"Sistema: online",20,104,10,C'88,214,141');
   SetLabel(Obj("MODE"),"Modo: "+(mode==""?"nao informado":mode)+" • MT5: "+(mt5==""?"nao confirmado":mt5),20,124,10,C'88,214,141');
   if(active_view=="CONFIG") SetLabel(Obj("INFO5"),"REAL: BLOQUEADO • autorizacao separada",20,441,9,C'255,155,155'); else if(ObjectFind(0,Obj("SAFE"))>=0) ObjectDelete(0,Obj("SAFE"));
   if(active_view=="RESERVA" || active_view=="ASSISTENTE" || active_view=="DECISION" || active_view=="REPLAY" || active_view=="SIMULATOR" || active_view=="KILL_SWITCH" || active_view=="UNAVAILABLE" || active_view=="MEMORIA" || active_view=="RISK" || active_view=="STATS" || active_view=="CONNECTIONS" || active_view=="ENVIRONMENT" || active_view=="SECURITY" || active_view=="REPORTS" || active_view=="AUDIT" || active_view=="FINANCE" || active_view=="DISCOVERIES") return;
   SetLabel(Obj("INFO1"),"Analise do ecossistema: "+(engine==""?"online":engine),20,361,9,C'205,215,230');
}
void RefreshMarketAssets(){
   string r; int code=0;
   if(!Http("GET","/api/market/assets","",r,code)){
      SetLabel(Obj("MARKET"),"Ativos/Mercados indisponiveis",20,278,8,C'255,118,118');
      return;
   }
   int total=0; int p=0;
   while(true){
      int hit=StringFind(r,"\"symbol\":",p);
      if(hit<0) break;
      total++; p=hit+9;
      if(total>999) break;
   }
   string source=JsonValue(r,"source");
   SetLabel(Obj("MARKET"),"Ativos/Mercados: "+IntegerToString(total)+" • "+(source==""?"MT5 DEMO":source),20,278,8,C'145,160,180');
}
void RefreshSecondary(){
   string r; int code=0;
   if(Http("GET","/api/risk","",r,code)){
      string allowed=JsonValue(r,"allowed");
      string reason=JsonValue(r,"reason");
      SetLabel(Obj("INFO2"),"Risco: "+(allowed=="true"?"PERMITIDO":"BLOQUEADO"),20,381,9,allowed=="true"?C'88,214,141':C'255,209,102');
   }else SetLabel(Obj("INFO2"),"Risco: indisponivel",20,381,9,C'255,118,118');

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
      SetLabel(Obj("INFO3"),"Memoria: registros "+(count==""?"disponiveis":count),20,401,9,C'205,215,230');
   }else SetLabel(Obj("INFO3"),"Memoria: indisponivel",20,401,9,C'255,118,118');
}
void SaveConfig(){
   string sym=ObjectFind(0,Obj("SYM"))>=0?ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT):_Symbol;
   string tf=ObjectFind(0,Obj("TF"))>=0?ObjectGetString(0,Obj("TF"),OBJPROP_TEXT):NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   tf=NormalizeTimeframe(tf);
   string leverage=leverage_enabled?"true":"false";
   string body="{\"selected_mode\":\"DEMO\",\"leverage_enabled\":"+leverage+",\"default_symbol\":\""+JsonEscape(sym)+"\",\"default_timeframe\":\""+JsonEscape(tf)+"\",\"require_closed_candle\":true,\"require_filters\":true}";
   string r; int code=0;
   if(Http("POST","/api/preferences/local",body,r,code)){
      SetLabel(Obj("INFO4"),"Configuracoes sincronizadas",20,421,9,C'88,214,141');
      RefreshPreferences();
   }else{
      SetLabel(Obj("INFO4"),"Nao foi possivel salvar configuracoes",20,421,9,C'255,118,118');
   }
}

void Analyze(bool render=true){
   string sym=_Symbol;
   string tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   if(ObjectFind(0,Obj("SYM"))>=0){
      string configured_symbol=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
      if(configured_symbol!="") sym=configured_symbol;
   }
   if(ObjectFind(0,Obj("TF"))>=0){
      string configured_timeframe=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
      if(configured_timeframe!="") tf=configured_timeframe;
   }
   tf=NormalizeTimeframe(tf);
   string body="{\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"limit\":100}";
   string r; int code=0;
   if(!Http("POST","/api/runtime/analysis/local",body,r,code)){
      runtime_ok=false;
      UpdateCompactSignal("INDISPONIVEL","",false);
      if(render) SetLabel(Obj("REASON"),"Analise indisponivel",20,204,9,C'255,118,118');
      return;
   }
   if(!health_ok){
      runtime_ok=false;
      UpdateCompactSignal("INDISPONIVEL","",false);
      if(render) SetLabel(Obj("REASON"),"Sistema indisponivel",20,204,9,C'255,118,118');
      return;
   }
   runtime_ok=true;
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   string score=JsonObjectValue(r,"quality","score");
   UpdateCompactSignal(signal,score,true);
   if(!render) return;
   string reason=JsonValue(r,"reason");
   color c=signal=="COMPRA"?C'88,214,141':signal=="VENDA"?C'255,118,118':C'255,209,102';
   SetLabel(Obj("SIGNAL"),CompactSignalText(signal),20,154,22,c);
   SetLabel(Obj("SCORE"),"Qualidade: "+(score==""?"—":DoubleToString(StringToDouble(score),0))+"%",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Analise concluida pelo ecossistema.":reason,0,62),20,204,9,C'180,190,205');
   SetLabel(Obj("INFO1"),"Decisao atualizada",20,361,9,c);
   ChartRedraw();
}
bool RefreshActiveCycleState(){
   if(last_cycle_id=="" || last_external_id=="") return true;
   string body="{\"cycle_id\":\""+JsonEscape(last_cycle_id)+"\",\"external_id\":\""+JsonEscape(last_external_id)+"\"}";
   string response; int code=0;
   if(!Http("POST","/api/runtime/close/local/reconcile",body,response,code)){
      SetLabel(Obj("INFO1"),"Estado da posicao inconclusivo; ciclo bloqueado.",20,361,9,C'255,118,118');
      return false;
   }
   string state=JsonObjectValue(response,"close_reconciliation","state");
   if(state=="CLOSED"){
      ClearCycleIdentity();
      SetLabel(Obj("INFO1"),"MT5 confirmou fechamento; novo ciclo liberado.",20,361,9,C'88,214,141');
      return cycle_identity_store_valid;
   }
   if(state=="OPEN"){
      SetLabel(Obj("INFO1"),"MT5 confirma posicao aberta; feche antes de novo ciclo.",20,361,9,C'255,209,102');
      return false;
   }
   SetLabel(Obj("INFO1"),"MT5 nao confirmou estado; ciclo permanece bloqueado.",20,361,9,C'255,118,118');
   return false;
}

void RunCycle(){
   if(!cycle_identity_store_valid){
      SetLabel(Obj("INFO1"),"Arquivo de ciclo indisponivel; novas execucoes bloqueadas.",20,361,9,C'255,118,118');
      return;
   }
   if(last_cycle_id!="" && last_external_id!="" && !RefreshActiveCycleState()){
      return;
   }
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   tf=NormalizeTimeframe(tf);
   string body="{\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"limit\":100,\"amount\":0.01,\"duration_seconds\":60}";
   string r; int code=0;
   SetLabel(Obj("INFO1"),"Validando ciclo DEMO...",20,361,9,C'255,209,102');
   if(!Http("POST","/api/runtime/cycle/local",body,r,code)){
      UpdateCompactSignal("INDISPONIVEL","",false);
      SetLabel(Obj("INFO1"),"Ciclo indisponivel ou bloqueado",20,361,9,C'255,118,118');
      return;
   }
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   string score=JsonObjectValue(r,"quality","score");
   UpdateCompactSignal(signal,score,true);
   string reason=JsonValue(r,"reason");
   string cid=JsonValue(r,"cycle_id");
   string eid=JsonValue(r,"external_id");
   string allowed=JsonValue(r,"execution_allowed");
   string accepted=JsonObjectValue(r,"execution","accepted");
   if(allowed=="true" && accepted=="true" && cid!="" && eid!=""){
      last_cycle_id=cid;
      last_external_id=eid;
      PersistCycleIdentity();
   }
   color c=signal=="COMPRA"?C'88,214,141':signal=="VENDA"?C'255,118,118':C'255,209,102';
   SetLabel(Obj("SIGNAL"),CompactSignalText(signal),20,154,22,c);
   SetLabel(Obj("SCORE"),"Qualidade: "+(score==""?"—":DoubleToString(StringToDouble(score),0))+"%",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Ciclo concluido.":reason,0,62),20,204,9,C'180,190,205');
   SetLabel(Obj("CYCLEID"),"Ciclo DEMO: "+(last_cycle_id==""?"sem posicao":"registrado"),20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: "+(last_external_id==""?"sem atividade":"registrada"),20,483,8,C'145,160,180');
   string timed_scheduled=JsonObjectValue(r,"timed_exit","scheduled");
   string timed_due=JsonObjectValue(r,"timed_exit","due_at");
   if(timed_scheduled=="true"){
      SetLabel(Obj("INFO1"),"Saida DEMO best-effort: "+StringSubstr(timed_due,0,19),20,361,9,C'88,214,141');
   }else{
      SetLabel(Obj("INFO1"),cycle_identity_store_valid?"Sem saida temporizada; fechamento manual explicito.":"Falha ao salvar ticket; não reinicie EA.",20,361,9,C'255,209,102');
   }
}
void CloseCycle(){
   if(last_cycle_id=="" || last_external_id==""){
      SetLabel(Obj("INFO1"),"Nao ha ciclo DEMO para fechar/reconciliar.",20,361,9,C'255,209,102');
      return;
   }
   string body="{\"cycle_id\":\""+JsonEscape(last_cycle_id)+"\",\"external_id\":\""+JsonEscape(last_external_id)+"\"}";
   string r; int code=0;
   if(Http("POST","/api/runtime/close/local",body,r,code)){
      if(JsonValue(r,"closed")=="true"){
         SetLabel(Obj("INFO1"),"Posicao DEMO fechada e confirmada.",20,361,9,C'88,214,141');
         ClearCycleIdentity();
         return;
      }
      string reconciliation; int reconcile_code=0;
      if(Http("POST","/api/runtime/close/local/reconcile",body,reconciliation,reconcile_code)){
         string state=JsonObjectValue(reconciliation,"close_reconciliation","state");
         if(state=="CLOSED"){
            SetLabel(Obj("INFO1"),"MT5 confirmou o fechamento.",20,361,9,C'88,214,141');
            ClearCycleIdentity();
         }else if(state=="OPEN"){
            SetLabel(Obj("INFO1"),"MT5 confirma: posicao continua aberta.",20,361,9,C'255,209,102');
         }else{
            SetLabel(Obj("INFO1"),"Fechamento inconclusivo; ciclo preservado.",20,361,9,C'255,118,118');
         }
      }else SetLabel(Obj("INFO1"),"Sem evidencia de fechamento; ciclo preservado.",20,361,9,C'255,118,118');
   }else{
      string reconciliation; int reconcile_code=0;
      if(Http("POST","/api/runtime/close/local/reconcile",body,reconciliation,reconcile_code)){
         string state=JsonObjectValue(reconciliation,"close_reconciliation","state");
         if(state=="CLOSED"){
            SetLabel(Obj("INFO1"),"MT5 confirmou o fechamento.",20,361,9,C'88,214,141');
            ClearCycleIdentity();
         }else if(state=="OPEN"){
            SetLabel(Obj("INFO1"),"MT5 confirma: posicao continua aberta.",20,361,9,C'255,209,102');
         }else{
            SetLabel(Obj("INFO1"),"Fechamento inconclusivo; ciclo preservado.",20,361,9,C'255,118,118');
         }
      }else SetLabel(Obj("INFO1"),"Fechamento bloqueado; identidade preservada.",20,361,9,C'255,118,118');
   }
}
int OnInit(){
   active_view="COCKPIT";
   active_area="COCKPIT";
   active_module="Operação";
   LoadCycleIdentity();
   LoadAssistantConversation();
   LoadPanelVisibility();
   if(panel_visible){
      Panel();
      RenderView();
   }else{
      RefreshPanelToggle();
   }
   EventSetTimer(MathMax(1,InpRefreshSeconds));
   RefreshHealth();
   if(panel_visible){ RefreshSecondary(); RefreshMarketAssets(); }
   // Prime runtime market-data state immediately, even when the native panel is hidden.
   Analyze(panel_visible);
   last_analysis_bar=iTime(_Symbol,_Period,0);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){
   EventKillTimer();
   DeletePanel();
}
void OnTimer(){
   if(!panel_visible){
      RefreshPanelToggle();
      RefreshHealth();
      Analyze(false);
      last_analysis_bar=iTime(_Symbol,_Period,0);
      return;
   }
   RefreshPanelLayout();
   RefreshPanelToggle();
   RefreshHealth();
   if(active_view=="COCKPIT") { RefreshSecondary(); RefreshMarketAssets(); }
   else if(active_view=="CONFIG") RefreshPreferences();
   else if(active_view=="NOTIF") RefreshNotifications();
   datetime current_bar=iTime(_Symbol,_Period,0);
   bool new_bar=(current_bar>0 && current_bar!=last_analysis_bar);
   if(new_bar) last_analysis_bar=current_bar;
   // Keep the compact signal fresh on every timer tick; render the larger
   // panel details only when a new bar arrives in the analysis views.
   Analyze(new_bar && (active_view=="COCKPIT" || active_view=="ANALISE"));
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(active_view=="COCKPIT" && bid>0) SetLabel(Obj("PRICE"),"Preco atual "+_Symbol+": "+DoubleToString(bid,_Digits),20,501,9,C'190,200,215');
}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   if(sparam==Obj("PANEL_TOGGLE") || sparam==Obj("PANEL_TOGGLE_BG")) { TogglePanel(); return; }
   if(sparam==Obj("A1")) { SelectArea("COCKPIT"); return; }
   else if(sparam==Obj("A2")) { SelectArea("ANÁLISE"); return; }
   else if(sparam==Obj("A3")) { SelectArea("ESTUDO"); return; }
   else if(sparam==Obj("A4")) { SelectArea("RESERVA FISCAL"); return; }
   else if(sparam==Obj("A5")) { SelectArea("ASSISTENTE DO ECOSSISTEMA"); return; }
   else if(sparam==Obj("A6")) { SelectArea("CENTRAL"); return; }
   else if(sparam==Obj("M1")) { SelectModule(0); return; }
   else if(sparam==Obj("M2")) { SelectModule(1); return; }
   else if(sparam==Obj("M3")) { SelectModule(2); return; }
   else if(sparam==Obj("M4")) { SelectModule(3); return; }
   else if(sparam==Obj("M5")) { SelectModule(4); return; }
   else if(sparam==Obj("M6")) { SelectModule(5); return; }
   else if(sparam==Obj("ASSISTANT_CONSENT")) { assistant_consent_armed=!assistant_consent_armed; SetButton(Obj("ASSISTANT_CONSENT"),assistant_consent_armed?"CONSENTIMENTO OPENAI: SIM":"CONSENTIMENTO OPENAI: NAO",20,307,220,28); }
   else if(sparam==Obj("ASSISTANT_SEND")) SendAssistantMessage();
   else if(sparam==Obj("KILL_CONFIRM") && active_view=="KILL_SWITCH") { kill_switch_confirm_armed=!kill_switch_confirm_armed; SetButton(Obj("KILL_CONFIRM"),kill_switch_confirm_armed?"CONFIRMACAO ARMADA":"CONFIRMAR BLOQUEIO",20,320,172,30); }
   else if(sparam==Obj("KILL_ACTIVATE") && active_view=="KILL_SWITCH") ActivateKillSwitch();
   else if(sparam==Obj("MEMORY_PREV")) { if(active_view=="MEMORIA" && memory_page>0) { memory_page--; RenderMemoryPage(); } }
   else if(sparam==Obj("MEMORY_NEXT")) { if(active_view=="MEMORIA" && (memory_page+1)*5<ArraySize(memory_records)) { memory_page++; RenderMemoryPage(); } }
   else if(sparam==Obj("ASSISTANT_PREV")) { if(active_view=="ASSISTENTE" && assistant_answer_page>0) { assistant_answer_page--; RenderAssistantAnswer(); } }
   else if(sparam==Obj("ASSISTANT_NEXT")) { if(active_view=="ASSISTENTE" && (assistant_answer_page+1)*330<StringLen(assistant_answer)) { assistant_answer_page++; RenderAssistantAnswer(); } }
   else if(sparam==Obj("REPLAY_RUN") && active_view=="REPLAY") RunHistoricalReplay();
   else if(sparam==Obj("SIM_RUN") && active_view=="SIMULATOR") RunHistoricalSimulator();
   else if(sparam==Obj("DISC_SAVE") && active_view=="DISCOVERIES") SaveDiscovery();
   else if(sparam==Obj("DISC_REFRESH") && active_view=="DISCOVERIES") RefreshDiscoveries();
   else if(sparam==Obj("ANALYZE")) {
      if(active_view=="DECISION") RefreshDecisionView();
      else if(active_view=="KILL_SWITCH") RefreshKillSwitchStatus();
      else if(active_view=="ANALISE") Analyze();
      else if(active_view=="CONFIG") RefreshPreferences();
      else if(active_view=="MEMORIA") RefreshMemory();
      else if(active_view=="RISK") RefreshRiskView();
      else if(active_view=="STATS") RefreshStatistics();
      else if(active_view=="CONNECTIONS") RefreshConnections();
      else if(active_view=="SECURITY") RefreshSecurityView();
      else if(active_view=="ENVIRONMENT") RefreshEnvironmentView();
      else if(active_view=="FINANCE") RefreshFinanceOverview();
      else if(active_view=="REPORTS") RefreshReports();
      else if(active_view=="AUDIT") RefreshAuditView();
      else if(active_view=="LAB") { RefreshHealth(); RefreshSecondary(); }
      else if(active_view=="ENSINO") RefreshLearning();
      else if(active_view=="DISCOVERIES") RefreshDiscoveries();
      else if(active_view=="NOTIF") RefreshNotifications();
      else if(active_view=="RESERVA") RefreshFiscal();
      else if(active_view=="ASSISTENTE") RefreshAssistantStatus();
      else Analyze();
   }
   else if(sparam==Obj("CYCLE")) { if(active_view=="COCKPIT") RunCycle(); }
   else if(sparam==Obj("SAVE")) { if(active_view=="CONFIG") SaveConfig(); }
   else if(sparam==Obj("LEVERAGE_TOGGLE")) { if(active_view=="CONFIG") { leverage_enabled=!leverage_enabled; SaveConfig(); } }
   else if(sparam==Obj("CLOSE")) { if(active_view=="COCKPIT") CloseCycle(); }
   else if(sparam==Obj("REC_REFRESH")) RefreshRecoveryInventory();
   else if(sparam==Obj("REC_PREV")){ recovery_selected=MathMax(0,recovery_selected-1); recovery_close_armed=false; RenderRecoverySelection(); }
   else if(sparam==Obj("REC_NEXT")){ recovery_selected=MathMin(ArraySize(recovery_items)-1,recovery_selected+1); recovery_close_armed=false; RenderRecoverySelection(); }
   else if(sparam==Obj("REC_RECONCILE")) ReconcileSelectedRecovery();
   else if(sparam==Obj("REC_CLOSE")) CloseSelectedRecovery();
}
