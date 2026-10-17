#property strict
#property version   "2.0"
#property description "Controlador Trading - interface nativa do ecossistema no grafico MT5."
#property description "Camada visual e operacional ligada ao runtime; DEMO por padrao."

input string InpRuntimeUrl = "http://127.0.0.1:8000";
input int    InpRefreshSeconds = 3;
input int    InpPanelWidth = 360;
input int    InpPanelHeight = 440;

string P="CTP_";
string last_cycle_id="";
string last_external_id="";
string active_view="COCKPIT";
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
string compact_score_raw="";
bool compact_available=false;
double panel_sx=1.0;
double panel_sy=1.0;

string Obj(string suffix){ return P+suffix; }
string PanelVisibilityKey(){ return P+IntegerToString(ChartID())+"_PANEL_VISIBLE"; }

int SX(int x){ return panel_x+(int)MathRound(x*panel_sx); }
int SY(int y){ return (int)MathRound(18+y*panel_sy); }
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
   panel_sy=(double)panel_height/620.0;
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
void SetCompactLabel(string name,string text,int x,int y,int size,color clr,bool clickable=false){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   // Anchor the compact controls to the chart's lower-left corner. Opening
   // the panel must never reposition the C, signal, or score.
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_LOWER);
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
string NormalizeCompactSignal(string raw){
   raw=StringTrimLeft(raw);
   raw=StringTrimRight(raw);
   StringToUpper(raw);
   StringReplace(raw,"Í","I");
   StringReplace(raw,"Á","A");
   StringReplace(raw,"É","E");
   StringReplace(raw,"Ó","O");
   StringReplace(raw,"Ú","U");
   StringReplace(raw,"Ç","C");
   if(raw=="COMPRA" || raw=="COMPRAR" || raw=="BUY") return "COMPRA";
   if(raw=="VENDA" || raw=="VENDER" || raw=="SELL") return "VENDA";
   if(raw=="AGUARDAR" || raw=="WAIT" || raw=="HOLD") return "AGUARDAR";
   if(raw=="INDISPONIVEL" || raw=="UNAVAILABLE") return "INDISPONIVEL";
   return "AGUARDAR";
}
bool ParseQualityScore(string raw,double &value){
   raw=StringTrimLeft(raw);
   raw=StringTrimRight(raw);
   if(raw=="") return false;
   bool digit=false;
   bool dot=false;
   for(int i=0;i<StringLen(raw);i++){
      ushort ch=StringGetCharacter(raw,i);
      if(ch>='0' && ch<='9'){ digit=true; continue; }
      if(ch=='.' && !dot){ dot=true; continue; }
      return false;
   }
   if(!digit) return false;
   value=StringToDouble(raw);
   return MathIsValidNumber(value) && value>=1.0 && value<=100.0;
}
void UpdateCompactSignal(string signal,string score,bool available=true){
   double parsed_score=0.0;
   bool score_valid=ParseQualityScore(score,parsed_score);
   string normalized_signal=NormalizeCompactSignal(signal);
   compact_signal=(available && (normalized_signal=="COMPRA" || normalized_signal=="VENDA" || normalized_signal=="AGUARDAR"))?(score_valid?normalized_signal:"AGUARDAR"):(available?"AGUARDAR":"INDISPONIVEL");
   compact_score_raw=(available && score_valid)?DoubleToString(parsed_score,2):"";
   compact_score=(available && score_valid)?DoubleToString(parsed_score,0)+"%":"—%";
   compact_available=available;
   if(ObjectFind(0,Obj("COMPACT_SIGNAL"))>=0){
      ObjectSetString(0,Obj("COMPACT_SIGNAL"),OBJPROP_TEXT,available?CompactSignalText(compact_signal):"INDISPONÍVEL");
      ObjectSetInteger(0,Obj("COMPACT_SIGNAL"),OBJPROP_COLOR,available?CompactSignalColor(compact_signal):C'255,118,118');
   }
   if(ObjectFind(0,Obj("COMPACT_SCORE"))>=0)
      ObjectSetString(0,Obj("COMPACT_SCORE"),OBJPROP_TEXT,compact_score);
}
void RefreshPanelToggle(){
   int cx=28;
   // Fixed distance from the lower edge in both open and closed states.
   int cy=46;
   // Preserve the approved C treatment: dark circular fill, cyan ring and cyan letter.
   SetCompactLabel(Obj("PANEL_TOGGLE_BG"),"●",cx,cy,39,C'5,15,27',false);
   SetCompactLabel(Obj("PANEL_TOGGLE_RING"),"◯",cx,cy,43,C'0,215,255',false);
   SetCompactLabel(Obj("PANEL_TOGGLE"),"C",cx,cy-1,20,C'0,215,255',true);
   SetCompactLabel(Obj("COMPACT_SIGNAL"),"AGUARDAR",cx+82,cy-2,13,C'255,209,102',false);
   SetCompactLabel(Obj("COMPACT_SCORE"),"—%",cx+220,cy-2,11,C'205,215,230',false);
   UpdateCompactSignal(compact_signal,compact_available?compact_score_raw:"",compact_available);
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
   panel_visible=false;
   GlobalVariableSet(PanelVisibilityKey(),0.0);
   RefreshPanelToggle();
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
   SetButton(Obj("V1"),"⌂",18,67,54,25);
   SetButton(Obj("V2"),"A",74,67,54,25);
   SetButton(Obj("V3"),"M",130,67,54,25);
   SetButton(Obj("V4"),"L",186,67,48,25);
   SetButton(Obj("V5"),"E",236,67,54,25);
   SetButton(Obj("V6"),"🔔",292,67,54,25);
   SetButton(Obj("V7"),"⚙",348,67,54,25);

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
}
void DeletePanel(bool preserveCompact=false){
   int total=ObjectsTotal(0,-1,-1);
   for(int i=total-1;i>=0;i--){
      string n=ObjectName(0,i,-1,-1);
      if(StringFind(n,P)!=0) continue;
      if(preserveCompact && (n==Obj("PANEL_TOGGLE") || n==Obj("PANEL_TOGGLE_BG") || n==Obj("PANEL_TOGGLE_RING") || n==Obj("COMPACT_SIGNAL") || n==Obj("COMPACT_SCORE"))) continue;
      ObjectDelete(0,n);
   }
   if(preserveCompact) RefreshPanelToggle();
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
string JsonObjectValue(string json,string objectKey,string key){
   string marker="\""+objectKey+"\":";
   int p=StringFind(json,marker);
   if(p<0) return "";
   int start=StringFind(json,"{",p+StringLen(marker));
   if(start<0) return "";
   int depth=0;
   bool inString=false;
   bool escaped=false;
   for(int i=start;i<StringLen(json);i++){
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
            if(depth==0) return JsonValue(StringSubstr(json,start,i-start+1),key);
         }
      }
   }
   return "";
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
   selected_mode=mode;
   leverage_enabled=(leverage=="true");
   SetButton(Obj("MODE_TOGGLE"),selected_mode=="REAL"?"MODO: REAL":"MODO: DEMO",20,465,172,28);
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
void RenderView(){
   if(active_view=="COCKPIT"){
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
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      Analyze();
      SetLabel(Obj("INFO2"),"Risco: "+(runtime_ok?"atualizado":"sistema indisponivel"),20,381,9,runtime_ok?C'205,215,230':C'255,118,118');
      SetLabel(Obj("INFO3"),"Fonte: analise atual do ecossistema",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Candle fechado + filtros: exigidos pelo payload",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Sem acao automatica a partir de notificacoes",20,441,9,C'205,215,230');
   }else if(active_view=="MEMORIA"){
      SetLabel(Obj("SUB"),"MEMORIA • historico, WIN/LOSS, estatisticas e auditoria",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR MEMORIA",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"ATUALIZAR ESTAT.",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshSecondary();
      SetLabel(Obj("INFO1"),"Memoria: registros disponiveis",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Risco: situacao atual",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Historico operacional atualizado",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Estatisticas atualizadas",20,421,9,C'205,215,230');
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
      SetLabel(Obj("INFO2"),"Risco: avaliacao atual",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Replay: disponivel no laboratorio",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Protecao operacional ativa",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Aprendizado separado da operacao",20,441,9,C'205,215,230');
   }else if(active_view=="ENSINO"){
      SetLabel(Obj("SUB"),"ENSINO • estudo separado da autorizacao operacional",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR ENSINO",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
      RefreshLearning();
   }else if(active_view=="NOTIF"){
      SetLabel(Obj("SUB"),"NOTIFICACOES • alertas e avisos do sistema",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR NOTIF.",20,284,172,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,284,177,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",20,320,172,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,320,177,28);
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
   string health=JsonValue(r,"health");
   string mode=JsonValue(r,"mode");
   string mt5=JsonValue(r,"mt5_demo");
   string engine=JsonValue(r,"decision_engine");
   string execution_allowed=JsonValue(r,"execution_allowed");
   string real=JsonValue(r,"real");
   health_ok=(health=="OK" || health=="WARNING") && mode=="SIMULACAO" && engine=="ONLINE" && execution_allowed=="false" && real=="DESABILITADO";
   if(!health_ok){
      runtime_ok=false;
      UpdateCompactSignal("INDISPONIVEL","",false);
      SetLabel(Obj("RUNTIME"),"Sistema: indisponivel",20,104,10,C'255,118,118');
      SetLabel(Obj("MODE"),"Modo: SIMULACAO • execucao bloqueada",20,124,10,C'255,209,102');
      if(active_view=="CONFIG") SetLabel(Obj("INFO5"),"REAL: BLOQUEADO • estado de saude invalido",20,441,9,C'255,155,155');
      else SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • estado de saude invalido",20,520,8,C'255,155,155');
      return;
   }
   runtime_ok=true;
   SetLabel(Obj("RUNTIME"),health=="OK"?"Sistema: online":"Sistema: limitado",20,104,10,health=="OK"?C'88,214,141':C'255,209,102');
   SetLabel(Obj("MODE"),"Modo: "+(mode==""?"SIMULACAO":mode)+" • MT5: "+(mt5==""?"DEMO":mt5),20,124,10,C'88,214,141');
   if(active_view=="CONFIG") SetLabel(Obj("INFO5"),"REAL: BLOQUEADO • autorizacao separada",20,441,9,C'255,155,155'); else if(ObjectFind(0,Obj("SAFE"))>=0) ObjectDelete(0,Obj("SAFE"));
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
   string body="{\"selected_mode\":\""+JsonEscape(selected_mode)+"\",\"leverage_enabled\":"+leverage+",\"default_symbol\":\""+JsonEscape(sym)+"\",\"default_timeframe\":\""+JsonEscape(tf)+"\",\"require_closed_candle\":true,\"require_filters\":true}";
   string r; int code=0;
   if(Http("POST","/api/preferences",body,r,code)){
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
   if(!Http("POST","/api/runtime/analysis",body,r,code)){
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
   signal=NormalizeCompactSignal(signal);
   string score=JsonObjectValue(r,"quality","score");
   double parsed_score=0.0;
   if(!ParseQualityScore(score,parsed_score)){ signal="AGUARDAR"; score=""; }
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
void RunCycle(){
   if(!health_ok){
      UpdateCompactSignal("INDISPONIVEL","",false);
      SetLabel(Obj("INFO1"),"Ciclo bloqueado: sistema indisponivel",20,361,9,C'255,118,118');
      return;
   }
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   tf=NormalizeTimeframe(tf);
   string body="{\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"limit\":100,\"amount\":0.01,\"duration_seconds\":60,\"confirmed\":true,\"filters_ok\":true,\"entry_conditions\":[]}";
   string r; int code=0;
   SetLabel(Obj("INFO1"),"Validando ciclo DEMO...",20,361,9,C'255,209,102');
   if(!Http("POST","/api/runtime/cycle",body,r,code)){
      UpdateCompactSignal("INDISPONIVEL","",false);
      SetLabel(Obj("INFO1"),"Ciclo indisponivel ou bloqueado",20,361,9,C'255,118,118');
      return;
   }
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   signal=NormalizeCompactSignal(signal);
   string score=JsonObjectValue(r,"quality","score");
   double parsed_score=0.0;
   if(!ParseQualityScore(score,parsed_score)){ signal="AGUARDAR"; score=""; }
   UpdateCompactSignal(signal,score,true);
   string reason=JsonValue(r,"reason");
   string cid=JsonValue(r,"cycle_id");
   string eid=JsonValue(r,"external_id");
   string allowed=JsonValue(r,"execution_allowed");
   color c=signal=="COMPRA"?C'88,214,141':signal=="VENDA"?C'255,118,118':C'255,209,102';
   SetLabel(Obj("SIGNAL"),CompactSignalText(signal),20,154,22,c);
   SetLabel(Obj("SCORE"),"Qualidade: "+(score==""?"—":DoubleToString(StringToDouble(score),0))+"%",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Ciclo concluido.":reason,0,62),20,204,9,C'180,190,205');
   last_cycle_id=cid; last_external_id=eid;
   SetLabel(Obj("CYCLEID"),"Ciclo DEMO: "+(cid==""?"concluido":"atualizado"),20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: "+(eid==""?"sem atividade":"registrada"),20,483,8,C'145,160,180');
   SetLabel(Obj("INFO1"),"Ciclo DEMO validado",20,361,9,C'205,215,230');
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
   }else SetLabel(Obj("INFO1"),"Fechamento bloqueado ou indisponivel",20,361,9,C'255,118,118');
}
int OnInit(){
   active_view="COCKPIT";
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
   if(bid>0) SetLabel(Obj("PRICE"),"Preco atual "+_Symbol+": "+DoubleToString(bid,_Digits),20,501,9,C'190,200,215');
}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   if(sparam==Obj("PANEL_TOGGLE") || sparam==Obj("PANEL_TOGGLE_BG")) { TogglePanel(); return; }
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
   else if(sparam==Obj("MODE_TOGGLE")) { selected_mode=(selected_mode=="DEMO"?"REAL":"DEMO"); SaveConfig(); }
   else if(sparam==Obj("LEVERAGE_TOGGLE")) { leverage_enabled=!leverage_enabled; SaveConfig(); }
   else if(sparam==Obj("CLOSE")) CloseCycle();
}
