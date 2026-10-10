#property strict
#property version   "2.0"
#property description "Controlador Trading - interface nativa do ecossistema no grafico MT5."
#property description "Camada visual e operacional ligada ao runtime; DEMO por padrao."

input string InpRuntimeUrl = "http://127.0.0.1:8000";
input int    InpRefreshSeconds = 3;
input int    InpPanelWidth = 440;
input int    InpPanelHeight = 440;

string P="CTP_";
string last_cycle_id="";
string last_external_id="";
string active_view="COCKPIT";
string active_nav="N1";
string current_signal="AGUARDAR";
bool runtime_ok=false;
datetime last_analysis_bar=0;
bool watermark_enabled=true;
bool panel_visible=true;
int panel_x=12;
int panel_y=18;
int panel_width=300;
int panel_height=440;
double panel_sx=1.0;
double panel_sy=1.0;

string Obj(string suffix){ return P+suffix; }
string WatermarkKey(){ return P+IntegerToString(ChartID())+"_WATERMARK"; }
string PanelVisibilityKey(){ return P+IntegerToString(ChartID())+"_PANEL_VISIBLE"; }

int SX(int x){ return panel_x+(int)MathRound(x*panel_sx); }
int SY(int y){ return panel_y+(int)MathRound(y*panel_sy); }
int SW(int w){ return MathMax(1,(int)MathRound(w*panel_sx)); }
int SH(int h){ return MathMax(1,(int)MathRound(h*panel_sy)); }
void RefreshPanelLayout(){
   int cw=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   // Painel flutuante compacto, ancorado embaixo à esquerda.
   panel_width=MathMin(InpPanelWidth,MathMax(360,(int)MathRound(cw*0.42)));
   panel_width=MathMin(panel_width,MathMax(300,cw-24));
   panel_height=MathMin(InpPanelHeight,MathMax(340,(int)MathRound(ch*0.48)));
   panel_height=MathMin(panel_height,MathMax(320,ch-90));
   panel_x=12;
   panel_y=MathMax(12,ch-panel_height-52);
   panel_sx=(double)panel_width/600.0;
   panel_sy=(double)panel_height/620.0;
   string bg=Obj("BG");
   if(ObjectFind(0,bg)>=0){
      ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,panel_x);
      ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,panel_y);
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
void ApplyWatermark(){
   string legacy=Obj("WATERMARK");
   string mark=Obj("WATERMARK_MARK");
   string name=Obj("WATERMARK_TEXT");
   if(ObjectFind(0,legacy)>=0) ObjectDelete(0,legacy);
   if(!watermark_enabled){
      if(ObjectFind(0,mark)>=0) ObjectDelete(0,mark);
      if(ObjectFind(0,name)>=0) ObjectDelete(0,name);
      return;
   }
   int w=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int h=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   int center_y=MathMax(120,h/2);

   // Marca horizontal, discreta e centralizada para não competir com os candles.
   if(ObjectFind(0,mark)<0) ObjectCreate(0,mark,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,mark,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,mark,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,mark,OBJPROP_XDISTANCE,MathMax(50,w/2-112));
   ObjectSetInteger(0,mark,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(0,mark,OBJPROP_FONTSIZE,16);
   ObjectSetInteger(0,mark,OBJPROP_COLOR,C'35,48,68');
   ObjectSetString(0,mark,OBJPROP_FONT,"Segoe UI Symbol");
   ObjectSetString(0,mark,OBJPROP_TEXT,"▂▅▇↗");
   ObjectSetInteger(0,mark,OBJPROP_BACK,true);
   ObjectSetInteger(0,mark,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,mark,OBJPROP_HIDDEN,true);

   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,MathMin(w-80,w/2+88));
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,10);
   ObjectSetInteger(0,name,OBJPROP_COLOR,C'38,46,60');
   ObjectSetString(0,name,OBJPROP_FONT,"Arial");
   ObjectSetString(0,name,OBJPROP_TEXT,"CONTROLADOR TRADING");
   ObjectSetInteger(0,name,OBJPROP_BACK,true);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void RefreshWatermarkControl(){
   if(active_view=="CONFIG") SetButton(Obj("WM"),watermark_enabled?"MARCA: ATIVADA":"MARCA: DESATIVADA",20,555,172,28);
   else if(ObjectFind(0,Obj("WM"))>=0) ObjectDelete(0,Obj("WM"));
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
   RefreshNavigation();
   RefreshWatermarkControl();
}
void RefreshPanelToggle(){
   string name=Obj("PANEL_TOGGLE");
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   int toggle_x=panel_visible?panel_x+panel_width-42:12;
   int toggle_y=panel_visible?panel_y+8:MathMax(12,ch-48);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,toggle_x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,toggle_y);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,32);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,32);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,17);
   ObjectSetInteger(0,name,OBJPROP_COLOR,C'63,224,255');
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,C'8,24,37');
   ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,C'38,210,242');
   ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,name,OBJPROP_TEXT,"C");
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   string signal_name=Obj("PANEL_SIGNAL");
   if(panel_visible){
      if(ObjectFind(0,signal_name)>=0) ObjectDelete(0,signal_name);
   }else{
      if(ObjectFind(0,signal_name)<0) ObjectCreate(0,signal_name,OBJ_LABEL,0,0,0);
      string signal=current_signal;
      color signal_color=C'255,209,102';
      if(signal=="COMPRA" || signal=="COMPRAR"){ signal="COMPRAR"; signal_color=C'54,226,130'; }
      else if(signal=="VENDA" || signal=="VENDER"){ signal="VENDER"; signal_color=C'255,86,101'; }
      else { signal="AGUARDAR"; signal_color=C'255,209,102'; }
      ObjectSetInteger(0,signal_name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
      ObjectSetInteger(0,signal_name,OBJPROP_XDISTANCE,52);
      ObjectSetInteger(0,signal_name,OBJPROP_YDISTANCE,MathMax(12,ch-38));
      ObjectSetInteger(0,signal_name,OBJPROP_FONTSIZE,11);
      ObjectSetInteger(0,signal_name,OBJPROP_COLOR,signal_color);
      ObjectSetString(0,signal_name,OBJPROP_FONT,"Segoe UI");
      ObjectSetString(0,signal_name,OBJPROP_TEXT,signal);
      ObjectSetInteger(0,signal_name,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0,signal_name,OBJPROP_HIDDEN,true);
   }
}
void TogglePanel(){
   panel_visible=!panel_visible;
   GlobalVariableSet(PanelVisibilityKey(),panel_visible?1.0:0.0);
   if(panel_visible){ Panel(); RenderView(); Analyze(true); }
   else DeletePanel(true,true);
   RefreshPanelToggle();
   ChartRedraw();
}
void LoadPanelVisibility(){
   if(GlobalVariableCheck(PanelVisibilityKey()))
      panel_visible=(GlobalVariableGet(PanelVisibilityKey())>0.5);
   RefreshPanelToggle();
}
void RefreshNavigation(){
   for(int i=1;i<=9;i++){
      string name=Obj("N"+IntegerToString(i));
      if(ObjectFind(0,name)<0) continue;
      bool selected=(active_nav=="N"+IntegerToString(i));
      ObjectSetInteger(0,name,OBJPROP_BGCOLOR,selected?C'14,73,96':C'24,32,44');
      ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,selected?C'38,210,242':C'55,72,92');
      ObjectSetInteger(0,name,OBJPROP_COLOR,selected?C'100,235,255':C'215,225,238');
   }
}
void Panel(){
   string bg=Obj("BG");
   if(ObjectFind(0,bg)<0) ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   RefreshPanelLayout();
   RefreshPanelToggle();
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,panel_x);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,panel_y);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,panel_width);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,panel_height);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,C'9,13,20');
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,C'55,65,85');
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_HIDDEN,true);

   SetLabel(Obj("BRAND_C"),"C",18,24,20,C'63,224,255');
   SetLabel(Obj("TITLE"),"CONTROLADOR TRADING",52,27,12,clrWhite);
   SetLabel(Obj("SUB"),"ECOSSISTEMA • DEMO / SIMULACAO",52,47,9,C'150,165,185');
   // Navegacao vertical no trilho direito; conteudo funcional preservado.
   SetButton(Obj("N1"),"COCKPIT",430,82,155,29);
   SetButton(Obj("N2"),"ANALISE",430,118,155,29);
   SetButton(Obj("N3"),"ESTUDO",430,154,155,29);
   SetButton(Obj("N4"),"LABORATORIO",430,190,155,29);
   SetButton(Obj("N5"),"REPLAY",430,226,155,29);
   SetButton(Obj("N6"),"MEMORIA",430,262,155,29);
   SetButton(Obj("N7"),"WIN/LOSS",430,298,155,29);
   SetButton(Obj("N8"),"ALAVANCAGEM",430,334,155,29);
   SetButton(Obj("N9"),"CONFIGURACOES",430,370,155,29);
   RefreshNavigation();

   SetLabel(Obj("RUNTIME"),"Runtime: verificando...",20,104,10,C'255,209,102');
   SetLabel(Obj("MODE"),"Modo: DEMO / SIMULACAO",20,124,10,C'88,214,141');
   SetLabel(Obj("SIGNAL"),"AGUARDAR",20,154,22,C'255,209,102');
   SetLabel(Obj("SCORE"),"Score: —/100",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),"Aguardando analise.",20,204,9,C'180,190,205');

   SetLabel(Obj("SYML"),"ATIVO",20,236,8,C'130,145,165');
   SetEdit(Obj("SYM"),_Symbol,20,249,150,25);
   SetLabel(Obj("TFL"),"TIMEFRAME",184,236,8,C'130,145,165');
   SetEdit(Obj("TF"),NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period)),184,249,195,25);
   SetLabel(Obj("MARKET"),"Ativos/Mercados: consultando...",20,278,8,C'145,160,180');

   SetButton(Obj("ANALYZE"),"ANALISAR NO RUNTIME",20,294,172,30);
   SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",202,294,177,30);
   SetButton(Obj("SAVE"),"SALVAR CONFIG",20,330,172,28);
   SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR",202,330,177,28);

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
void DeletePanel(bool preserveWatermark=false,bool preserveToggle=false){
   int total=ObjectsTotal(0,-1,-1);
   for(int i=total-1;i>=0;i--){
      string n=ObjectName(0,i,-1,-1);
      if(StringFind(n,P)!=0) continue;
      if(preserveToggle && n==Obj("PANEL_TOGGLE")) continue;
      if(preserveWatermark && (n==Obj("WATERMARK_MARK") || n==Obj("WATERMARK_TEXT"))) continue;
      ObjectDelete(0,n);
   }
   if(preserveToggle) RefreshPanelToggle();
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
      SetLabel(Obj("INFO5"),"Analise operacional atualizada pelo runtime",20,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Notificacoes: indisponiveis • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
   }
}
void RefreshLearning(){
   string r; int code=0;
   if(Http("GET","/api/learning","",r,code)){
      string progress=JsonValue(r,"progress");
      string active=JsonValue(r,"active_module");
      SetLabel(Obj("INFO1"),"Estudo: "+(active==""?"trilha disponivel":active),20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Progresso: "+(progress==""?"—":progress),20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Aprendizado separado da autorizacao operacional.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"learning_authorizes_trading=false",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"Historico operacional atualizado",20,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Estudo: runtime indisponivel • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
   }
}
void RenderView(){
   RefreshNavigation();
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
      SetLabel(Obj("INFO3"),"Fonte da leitura: endpoint /api/runtime/analysis",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Candle fechado + filtros: exigidos pelo payload",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Sem acao automatica a partir de notificacoes",20,441,9,C'205,215,230');
   }else if(active_view=="MEMORIA"){
      SetLabel(Obj("SUB"),active_nav=="N7"?"WIN/LOSS • resultados, estatisticas e auditoria":"MEMORIA • historico, WIN/LOSS, estatisticas e auditoria",20,47,9,C'150,165,185');
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
      SetLabel(Obj("INFO3"),"Replay: endpoint nativo ainda nao validado",20,401,9,C'255,209,102');
      SetLabel(Obj("INFO4"),"Execution Gate: controle operacional ativo",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Aprendizado separado da operacao",20,441,9,C'205,215,230');
   }else if(active_view=="REPLAY"){
      SetLabel(Obj("SUB"),"REPLAY • ligacao nativa ainda nao confirmada",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"VERIFICAR AMBIENTE",20,284,172,30);
      SetLabel(Obj("INFO1"),"Replay nao tem tela nativa ligada neste EA.",20,361,9,C'255,209,102');
      SetLabel(Obj("INFO2"),"Esta tela nao executa nem simula replay.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"A ligacao precisa ser validada no runtime.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Nenhum resultado de replay foi inventado.",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
   }else if(active_view=="ALAVANCAGEM"){
      SetLabel(Obj("SUB"),"ALAVANCAGEM • modulo web nao ligado ao EA nativo",20,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Integracao nativa nao confirmada.",20,361,9,C'255,209,102');
      SetLabel(Obj("INFO2"),"Esta tela nao altera alavancagem.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Execucao autorizada: false.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Barreiras operacionais preservadas.",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",20,441,9,C'255,155,155');
      if(ObjectFind(0,Obj("ANALYZE"))>=0) ObjectDelete(0,Obj("ANALYZE"));
      if(ObjectFind(0,Obj("CYCLE"))>=0) ObjectDelete(0,Obj("CYCLE"));
      if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
      if(ObjectFind(0,Obj("CLOSE"))>=0) ObjectDelete(0,Obj("CLOSE"));
   }else if(active_view=="ENSINO"){
      SetLabel(Obj("SUB"),"ESTUDO • aprendizado separado da autorizacao operacional",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR ESTUDO",20,284,172,30);
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
   if(active_view!="CONFIG" && active_view!="MEMORIA"){
      if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
   }
   if(active_view!="CONFIG"){
      if(ObjectFind(0,Obj("WM"))>=0) ObjectDelete(0,Obj("WM"));
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
   if(active_view=="CONFIG") SetLabel(Obj("SAFE"),"REAL: "+(real==""?"DESABILITADO":real)+" • Execucao: "+(exec==""?"BLOQUEADA":exec),20,520,8,C'255,155,155'); else if(ObjectFind(0,Obj("SAFE"))>=0) ObjectDelete(0,Obj("SAFE"));
   SetLabel(Obj("INFO1"),"Motor de decisao: "+(engine==""?"ONLINE":engine),20,361,9,C'205,215,230');
}
void RefreshMarketAssets(){
   string r; int code=0;
   if(!Http("GET","/api/market/assets","",r,code)){
      SetLabel(Obj("MARKET"),"Ativos/Mercados: indisponiveis • HTTP "+IntegerToString(code),20,278,8,C'255,118,118');
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
      // The endpoint returns a limited records array; it does not promise a total count.
      SetLabel(Obj("INFO3"),"Memoria: resposta recebida do runtime",20,401,9,C'205,215,230');
   }else SetLabel(Obj("INFO3"),"Memoria: indisponivel",20,401,9,C'255,118,118');
}
void SaveConfig(){
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   tf=NormalizeTimeframe(tf);
   string body="{\"selected_mode\":\"DEMO\",\"default_symbol\":\""+JsonEscape(sym)+"\",\"default_timeframe\":\""+JsonEscape(tf)+"\",\"require_closed_candle\":true,\"require_filters\":true}";
   string r; int code=0;
   if(Http("POST","/api/preferences",body,r,code))
      SetLabel(Obj("INFO1"),"Configuracoes sincronizadas no runtime • HTTP "+IntegerToString(code),20,361,9,C'88,214,141');
   else
      SetLabel(Obj("INFO1"),"Falha ao sincronizar configuracoes • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
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
      // A failed analysis invalidates the last analysis health state as well as its signal.
      runtime_ok=false;
      // Never leave a stale BUY/SELL visible when the latest analysis failed.
      current_signal="AGUARDAR";
      RefreshPanelToggle();
      if(render){
         SetLabel(Obj("SIGNAL"),current_signal,20,154,22,C'255,209,102');
         SetLabel(Obj("REASON"),"Analise indisponivel • HTTP "+IntegerToString(code),20,204,9,C'255,118,118');
      }
      return;
   }
   runtime_ok=true;
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   current_signal=(signal=="COMPRA" || signal=="COMPRAR")?"COMPRAR":(signal=="VENDA" || signal=="VENDER")?"VENDER":"AGUARDAR";
   // Keep the compact C signal current even when the full panel is hidden.
   RefreshPanelToggle();
   if(!render) return;
   string score=JsonValue(r,"score");
   string reason=JsonValue(r,"reason");
   color c=current_signal=="COMPRAR"?C'88,214,141':current_signal=="VENDER"?C'255,118,118':C'255,209,102';
   SetLabel(Obj("SIGNAL"),current_signal,20,154,22,c);
   SetLabel(Obj("SCORE"),"Score: "+(score==""?"—":score)+"/100",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Analise concluida pelo runtime.":reason,0,62),20,204,9,C'180,190,205');
   SetLabel(Obj("INFO1"),"Decisao: "+signal+" • score "+(score==""?"—":score)+" • origem runtime",20,361,9,c);
   ChartRedraw();
}
void RunCycle(){
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   tf=NormalizeTimeframe(tf);
   // This native EA has no explicit closed-candle confirmation or filter checklist UI.
   // Fail closed instead of asserting that required safeguards passed.
   string body="{\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"limit\":100,\"amount\":0.01,\"duration_seconds\":60,\"confirmed\":false,\"filters_ok\":false,\"entry_conditions\":[]}";
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
   current_signal=(signal=="COMPRA" || signal=="COMPRAR")?"COMPRAR":(signal=="VENDA" || signal=="VENDER")?"VENDER":"AGUARDAR";
   color c=current_signal=="COMPRAR"?C'88,214,141':current_signal=="VENDER"?C'255,86,101':C'255,209,102';
   SetLabel(Obj("SIGNAL"),current_signal,20,154,22,c);
   RefreshPanelToggle();
   SetLabel(Obj("SCORE"),"Score: "+(score==""?"—":score)+"/100",20,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Ciclo concluido.":reason,0,62),20,204,9,C'180,190,205');
   last_cycle_id=cid; last_external_id=eid;
   SetLabel(Obj("CYCLEID"),"Ciclo: "+(cid==""?"—":cid),20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: "+(eid==""?"—":eid),20,483,8,C'145,160,180');
   SetLabel(Obj("INFO1"),"Ciclo DEMO: "+signal+" • execucao aceita="+(allowed==""?"false":allowed),20,361,9,allowed=="true"?C'88,214,141':C'255,209,102');
}
void CloseCycle(){
   if(last_cycle_id=="" || last_external_id==""){
      SetLabel(Obj("INFO1"),"Nao ha ciclo DEMO para fechar/reconciliar.",20,361,9,C'255,209,102');
      return;
   }
   string body="{\"cycle_id\":\""+JsonEscape(last_cycle_id)+"\",\"external_id\":\""+JsonEscape(last_external_id)+"\"}";
   string r; int code=0;
   if(Http("POST","/api/runtime/close",body,r,code)){
      string closed=JsonValue(r,"closed");
      if(closed=="true"){
         SetLabel(Obj("INFO1"),"Fechamento DEMO confirmado • reconciliacao solicitada.",20,361,9,C'88,214,141');
         last_cycle_id=""; last_external_id="";
      }else{
         string message=JsonValue(r,"message");
         SetLabel(Obj("INFO1"),"Fechamento nao confirmado: "+StringSubstr(message==""?"runtime nao aceitou a operacao":message,0,42),20,361,9,C'255,118,118');
      }
   }else SetLabel(Obj("INFO1"),"Fechamento falhou/bloqueado • HTTP "+IntegerToString(code),20,361,9,C'255,118,118');
}
int OnInit(){
   active_view="COCKPIT";
   LoadWatermark();
   LoadPanelVisibility();
   if(panel_visible){
      Panel();
      RenderView();
   }else{
      RefreshPanelToggle();
   }
   EventSetTimer(MathMax(1,InpRefreshSeconds));
   RefreshHealth();
   RefreshSecondary();
   RefreshMarketAssets();
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
      ApplyWatermark();
      datetime hidden_bar=iTime(_Symbol,_Period,0);
      if(hidden_bar>0 && hidden_bar!=last_analysis_bar){
         last_analysis_bar=hidden_bar;
         Analyze(false);
      }
      return;
   }
   RefreshPanelLayout();
   RefreshPanelToggle();
   RefreshHealth();
   if(active_view=="COCKPIT") { RefreshSecondary(); RefreshMarketAssets(); }
   else if(active_view=="CONFIG") RefreshPreferences();
   else if(active_view=="NOTIF") RefreshNotifications();
   datetime current_bar=iTime(_Symbol,_Period,0);
   if(current_bar>0 && current_bar!=last_analysis_bar){
      last_analysis_bar=current_bar;
      // Refresh from broker once per new chart bar, not every timer tick.
      Analyze(active_view=="COCKPIT" || active_view=="ANALISE");
   }
   ApplyWatermark();
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(bid>0) SetLabel(Obj("PRICE"),"Preco atual "+_Symbol+": "+DoubleToString(bid,_Digits),20,501,9,C'190,200,215');
}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   if(id==CHARTEVENT_CHART_CHANGE){
      if(panel_visible){ Panel(); RenderView(); }
      RefreshPanelToggle();
      ApplyWatermark();
      ChartRedraw();
      return;
   }
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   if(sparam==Obj("PANEL_TOGGLE")) { TogglePanel(); return; }
   if(sparam==Obj("N1")) { active_nav="N1"; active_view="COCKPIT"; RenderView(); }
   else if(sparam==Obj("N2")) { active_nav="N2"; active_view="ANALISE"; RenderView(); }
   else if(sparam==Obj("N3")) { active_nav="N3"; active_view="ENSINO"; RenderView(); }
   else if(sparam==Obj("N4")) { active_nav="N4"; active_view="LAB"; RenderView(); }
   else if(sparam==Obj("N5")) { active_nav="N5"; active_view="REPLAY"; RenderView(); }
   else if(sparam==Obj("N6")) { active_nav="N6"; active_view="MEMORIA"; RenderView(); }
   else if(sparam==Obj("N7")) { active_nav="N7"; active_view="MEMORIA"; RenderView(); }
   else if(sparam==Obj("N8")) { active_nav="N8"; active_view="ALAVANCAGEM"; RenderView(); }
   else if(sparam==Obj("N9")) { active_nav="N9"; active_view="CONFIG"; RenderView(); }
   else if(sparam==Obj("ANALYZE")) {
      if(active_view=="ANALISE") Analyze();
      else if(active_view=="CONFIG") RefreshPreferences();
      else if(active_view=="MEMORIA") RefreshSecondary();
      else if(active_view=="LAB") { RefreshHealth(); RefreshSecondary(); }
      else if(active_view=="REPLAY") RefreshHealth();
      else if(active_view=="ALAVANCAGEM") { /* Informational only; no native integration. */ }
      else if(active_view=="ENSINO") RefreshLearning();
      else if(active_view=="NOTIF") RefreshNotifications();
      else Analyze();
   }
   else if(sparam==Obj("CYCLE")) RunCycle();
   else if(sparam==Obj("SAVE")) {
      if(active_view=="MEMORIA") RefreshSecondary();
      else if(active_view=="CONFIG") SaveConfig();
   }
   else if(sparam==Obj("CLOSE")) CloseCycle();
   else if(sparam==Obj("WM")) ToggleWatermark();
}
