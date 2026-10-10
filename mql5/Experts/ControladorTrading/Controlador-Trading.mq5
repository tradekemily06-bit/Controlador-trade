#property strict
#include <Canvas\Canvas.mqh>
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
string current_quality_score="";
string current_quality_level="";
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
CCanvas controller_canvas;
int controller_canvas_size=0;
bool controller_canvas_ready=false;

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
   int available_w=MathMax(240,cw-24);
   int available_h=MathMax(220,ch-90);
   // The open ecosystem must remain a compact overlay, never a half-screen takeover.
   panel_width=MathMin(available_w,MathMin(MathMax(540,InpPanelWidth),MathMax(240,(int)MathRound(cw*0.42))));
   panel_height=MathMin(available_h,MathMin(MathMax(440,InpPanelHeight),MathMax(220,(int)MathRound(ch*0.44))));
   panel_width=MathMax(240,panel_width);
   panel_height=MathMax(220,panel_height);
   panel_x=12;
   panel_y=MathMax(12,ch-panel_height-52);
   panel_sx=(double)panel_width/540.0;
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
   // Marca d'agua diagonal e responsiva, alinhada ao brilho azul/ciano do ecossistema.
   // Mantida no fundo e dimensionada pela area real do grafico para desktop e janelas menores.
   double wm_scale=MathMin((double)w/1180.0,(double)h/650.0);
   wm_scale=MathMax(0.72,MathMin(1.42,wm_scale));
   int wm_icon_size=(int)MathRound(46.0*wm_scale);
   int wm_text_size=(int)MathRound(34.0*wm_scale);
   int center_x=w/2;
   int center_y=(int)MathRound(h*0.52);
   int icon_x=MathMax(18,center_x-(int)MathRound(245.0*wm_scale));
   int text_x=MathMin(w-18,center_x+(int)MathRound(105.0*wm_scale));
   // ANGLE is applied to both elements so the icon and full wordmark share one diagonal.
   double wm_angle=330.0;

   if(ObjectFind(0,mark)<0) ObjectCreate(0,mark,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,mark,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,mark,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,mark,OBJPROP_XDISTANCE,icon_x);
   ObjectSetInteger(0,mark,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(0,mark,OBJPROP_ANGLE,wm_angle);
   ObjectSetInteger(0,mark,OBJPROP_FONTSIZE,wm_icon_size);
   ObjectSetInteger(0,mark,OBJPROP_COLOR,C'36,150,190');
   ObjectSetString(0,mark,OBJPROP_FONT,"Segoe UI Symbol");
   ObjectSetString(0,mark,OBJPROP_TEXT,"▂▅▇↗");
   ObjectSetInteger(0,mark,OBJPROP_BACK,true);
   ObjectSetInteger(0,mark,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,mark,OBJPROP_HIDDEN,true);

   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,text_x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(0,name,OBJPROP_ANGLE,wm_angle);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,wm_text_size);
   ObjectSetInteger(0,name,OBJPROP_COLOR,C'35,135,175');
   ObjectSetString(0,name,OBJPROP_FONT,"Arial");
   ObjectSetString(0,name,OBJPROP_TEXT,"CONTROLADOR TRADING");
   ObjectSetInteger(0,name,OBJPROP_BACK,true);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void RefreshWatermarkControl(){
   // No extra watermark button may remain on the chart when C is closed.
   string legacy=Obj("WM");
   if(ObjectFind(0,legacy)>=0) ObjectDelete(0,legacy);
   // The independent watermark switch lives inside C > Configurações only.
   if(panel_visible && active_view=="CONFIG" && ObjectFind(0,Obj("CYCLE"))>=0)
      ObjectSetString(0,Obj("CYCLE"),OBJPROP_TEXT,watermark_enabled?"MARCA: ON":"MARCA: OFF");
   ApplyWatermark();
}
void ToggleWatermark(){
   watermark_enabled=!watermark_enabled;
   GlobalVariableSet(WatermarkKey(),watermark_enabled?1.0:0.0);
   string body="{\"watermark_enabled\":"+(watermark_enabled?"true":"false")+"}";
   string response; int code=0;
   bool synced=Http("POST","/api/preferences",body,response,code);
   RefreshWatermarkControl();
   if(panel_visible)
      SetLabel(Obj("INFO1"),synced?(watermark_enabled?"Marca d'agua ativada e sincronizada.":"Marca d'agua desativada e sincronizada."):"Marca alterada neste MT5; sincronizacao indisponivel.",180,361,9,synced?C'88,214,141':C'255,209,102');
   ChartRedraw();
}
void LoadWatermark(){
   if(GlobalVariableCheck(WatermarkKey()))
      watermark_enabled=(GlobalVariableGet(WatermarkKey())>0.5);
   // Shared runtime preference is authoritative when available; local state is a safe fallback.
   string response; int code=0;
   if(Http("GET","/api/preferences","",response,code)){
      string shared=JsonValue(response,"watermark_enabled");
      if(shared=="true" || shared=="false"){
         watermark_enabled=(shared=="true");
         GlobalVariableSet(WatermarkKey(),watermark_enabled?1.0:0.0);
      }
   }
   RefreshNavigation();
   RefreshWatermarkControl();
}
void RefreshPanelToggle(){
   string name=Obj("PANEL_TOGGLE");
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   int cw=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   double c_scale=MathMax(0.90,MathMin(1.20,MathMin((double)cw/1100.0,(double)ch/650.0)));
   int c_size=(int)MathRound(38.0*c_scale);
   // C stays anchored at the lower-left in both states; opening it does not move the control.
   int toggle_x=12;
   int toggle_y=MathMax(12,ch-c_size-12);

   // A CCanvas bitmap is a pixel-anchored, clickable chart label. OBJ_ELLIPSE
   // is a time/price drawing object and must not be used as a screen button.
   if(controller_canvas_ready && controller_canvas_size!=c_size){
      controller_canvas.Destroy();
      controller_canvas_ready=false;
      controller_canvas_size=0;
   }
   if(!controller_canvas_ready){
      if(ObjectFind(0,name)>=0) ObjectDelete(0,name);
      if(!controller_canvas.CreateBitmapLabel(0,0,name,toggle_x,toggle_y,c_size,c_size,COLOR_FORMAT_ARGB_NORMALIZE))
         return;
      controller_canvas_ready=true;
      controller_canvas_size=c_size;
   }
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,toggle_x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,toggle_y);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,true);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,name,OBJPROP_BACK,false);

   controller_canvas.Erase(ColorToARGB(C'8,24,37',0));
   int center=c_size/2;
   int outer_radius=MathMax(2,center-1);
   int inner_radius=MathMax(1,outer_radius-3);
   controller_canvas.FillCircle(center,center,outer_radius,ColorToARGB(C'38,210,242',255));
   controller_canvas.FillCircle(center,center,inner_radius,ColorToARGB(C'8,24,37',255));
   controller_canvas.FontSet("Segoe UI",MathMax(12,(int)MathRound(18.0*c_scale)));
   controller_canvas.TextOut(center-5,center-11,"C",ColorToARGB(C'63,224,255',255));
   controller_canvas.Update();

   string signal_name=Obj("PANEL_SIGNAL");
   if(ObjectFind(0,signal_name)<0) ObjectCreate(0,signal_name,OBJ_LABEL,0,0,0);
   string signal=current_signal;
   color signal_color=C'255,209,102';
   if(signal=="COMPRA" || signal=="COMPRAR"){ signal="COMPRAR"; signal_color=C'54,226,130'; }
   else if(signal=="VENDA" || signal=="VENDER"){ signal="VENDER"; signal_color=C'255,86,101'; }
   else { signal="AGUARDAR"; signal_color=C'255,209,102'; }
   if(current_quality_score!="") signal+=" "+current_quality_score+"%";
   if(current_quality_level!="") signal+=" "+current_quality_level;
   // The signal and its quality remain beside C, with no extra heading or status label.
   int signal_x=c_size+20;
   int signal_y=toggle_y+MathMax(8,(c_size-18)/2);
   ObjectSetInteger(0,signal_name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,signal_name,OBJPROP_XDISTANCE,signal_x);
   ObjectSetInteger(0,signal_name,OBJPROP_YDISTANCE,signal_y);
   ObjectSetInteger(0,signal_name,OBJPROP_FONTSIZE,10);
   ObjectSetInteger(0,signal_name,OBJPROP_COLOR,signal_color);
   ObjectSetString(0,signal_name,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,signal_name,OBJPROP_TEXT,signal);
   ObjectSetInteger(0,signal_name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,signal_name,OBJPROP_HIDDEN,true);
}
void TogglePanel(){
   panel_visible=!panel_visible;
   GlobalVariableSet(PanelVisibilityKey(),panel_visible?1.0:0.0);
   if(panel_visible){ Panel(); RenderView(); Analyze(true); }
   else DeletePanel(true,true);
   RefreshPanelToggle();
   RefreshWatermarkControl();
   ChartRedraw();
}
void LoadPanelVisibility(){
   // Start with the chart unobstructed every time the EA initializes.
   panel_visible=false;
   GlobalVariableSet(PanelVisibilityKey(),0.0);
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
   // Navegacao vertical no trilho esquerdo; conteudo funcional preservado.
   SetButton(Obj("N1"),"COCKPIT",20,82,145,29);
   SetButton(Obj("N2"),"ANALISE",20,118,145,29);
   SetButton(Obj("N3"),"ESTUDO",20,154,145,29);
   SetButton(Obj("N4"),"LABORATORIO",20,190,145,29);
   SetButton(Obj("N5"),"REPLAY",20,226,145,29);
   SetButton(Obj("N6"),"MEMORIA",20,262,145,29);
   SetButton(Obj("N7"),"WIN/LOSS",20,298,145,29);
   SetButton(Obj("N8"),"ALAVANCAGEM",20,334,145,29);
   SetButton(Obj("N9"),"CONFIGURACOES",20,370,145,29);
   RefreshNavigation();

   SetLabel(Obj("RUNTIME"),"Runtime: verificando...",180,104,10,C'255,209,102');
   SetLabel(Obj("MODE"),"Modo: DEMO / SIMULACAO",180,124,10,C'88,214,141');
   SetLabel(Obj("SIGNAL"),"AGUARDAR",180,154,22,C'255,209,102');
   SetLabel(Obj("SCORE"),"Score: —/100",180,184,10,clrWhite);
   SetLabel(Obj("REASON"),"Aguardando analise.",180,204,9,C'180,190,205');

   SetLabel(Obj("SYML"),"ATIVO",180,236,8,C'130,145,165');
   SetEdit(Obj("SYM"),_Symbol,180,249,100,25);
   SetLabel(Obj("TFL"),"TIMEFRAME",290,236,8,C'130,145,165');
   SetEdit(Obj("TF"),NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period)),290,249,120,25);
   SetLabel(Obj("MARKET"),"Ativos/Mercados: consultando...",180,278,8,C'145,160,180');

   SetButton(Obj("ANALYZE"),"ANALISAR RUNTIME",180,294,110,30);
   SetButton(Obj("CYCLE"),"CICLO DEMO",296,294,114,30);
   SetButton(Obj("SAVE"),"SALVAR CONFIG",180,330,110,28);
   SetButton(Obj("CLOSE"),"FECHAR/RECONC.",296,330,114,28);

   SetLabel(Obj("INFO1"),"Decisao: —",180,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Risk Gate: verificando...",180,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Memoria: verificando...",180,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Estatisticas: verificando...",180,421,9,C'205,215,230');
   SetLabel(Obj("INFO5"),"Noticias: verificando...",180,441,9,C'205,215,230');

   SetLabel(Obj("CYCLEID"),"Ciclo: —",180,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: —",180,483,8,C'145,160,180');
   SetLabel(Obj("PRICE"),"Preco atual: —",180,501,9,C'190,200,215');
   SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • barreiras mantidas",180,520,8,C'255,155,155');
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

string JsonObjectValue(string json,string key){
   string needle="\"" + key + "\"";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   while(p<StringLen(json) && (StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\n' || StringGetCharacter(json,p)=='\r' || StringGetCharacter(json,p)=='\t')) p++;
   if(p>=StringLen(json) || StringGetCharacter(json,p)!=':') return "";
   p++;
   while(p<StringLen(json) && (StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\n' || StringGetCharacter(json,p)=='\r' || StringGetCharacter(json,p)=='\t')) p++;
   if(p>=StringLen(json) || StringGetCharacter(json,p)!='{') return "";
   int start=p, depth=0;
   bool in_string=false, escaped=false;
   for(int i=p;i<StringLen(json);i++){
      ushort c=StringGetCharacter(json,i);
      if(in_string){
         if(escaped) escaped=false;
         else if(c=='\\') escaped=true;
         else if(c=='"') in_string=false;
         continue;
      }
      if(c=='"'){ in_string=true; continue; }
      if(c=='{') depth++;
      else if(c=='}'){
         depth--;
         if(depth==0) return StringSubstr(json,start,i-start+1);
      }
   }
   return "";
}
string JsonValue(string json,string key){
   string needle="\"" + key + "\"";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   // Accept standard JSON whitespace around the colon and value.
   while(p<StringLen(json) && (StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\n' || StringGetCharacter(json,p)=='\r' || StringGetCharacter(json,p)=='\t')) p++;
   if(p>=StringLen(json) || StringGetCharacter(json,p)!=':') return "";
   p++;
   while(p<StringLen(json) && (StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\n' || StringGetCharacter(json,p)=='\r' || StringGetCharacter(json,p)=='\t')) p++;
   if(p>=StringLen(json)) return "";
   if(StringGetCharacter(json,p)=='"'){
      int q=p+1;
      while(q<StringLen(json)){
         if(StringGetCharacter(json,q)=='"' && (q==p+1 || StringGetCharacter(json,q-1)!='\\')) break;
         q++;
      }
      if(q>=StringLen(json)) return "";
      return StringSubstr(json,p+1,q-p-1);
   }
   int q=p;
   while(q<StringLen(json)){
      ushort c=StringGetCharacter(json,q);
      if(c==',' || c=='}' || c==']' || c=='\n' || c=='\r' || c==' ' || c=='\t') break;
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
      SetLabel(Obj("INFO1"),"Configuracoes: runtime indisponivel • HTTP "+IntegerToString(code),180,361,9,C'255,118,118');
      return;
   }
   string mode=JsonValue(r,"selected_mode");
   string sym=JsonValue(r,"default_symbol");
   string tf=JsonValue(r,"default_timeframe");
   string closed=JsonValue(r,"require_closed_candle");
   string filters=JsonValue(r,"require_filters");
   SetLabel(Obj("INFO1"),"Modo: "+(mode==""?"DEMO":mode)+" • simbolo: "+(sym==""?"—":sym),180,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Timeframe: "+(tf==""?"—":tf)+" • candle fechado: "+(closed==""?"—":closed),180,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Filtros obrigatorios: "+(filters==""?"—":filters),180,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Marca d'agua: "+(watermark_enabled?"ATIVADA":"DESATIVADA")+" • persistencia local MT5",180,421,9,watermark_enabled?C'88,214,141':C'145,160,180');
   SetLabel(Obj("INFO5"),"REAL: bloqueado • preferencias nao concedem autoridade REAL",180,441,9,C'255,155,155');
}
void RefreshNotifications(){
   string r; int code=0;
   if(Http("GET","/api/notifications","",r,code)){
      string unread=JsonValue(r,"unread");
      string total=JsonValue(r,"total");
      SetLabel(Obj("INFO1"),"Notificacoes: "+(total==""?"disponiveis":total)+" • nao lidas "+(unread==""?"—":unread),180,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Eventos priorizados pelo runtime.",180,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Sem acao automatica a partir de notificacoes.",180,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Atualizacao: HTTP "+IntegerToString(code),180,421,9,C'88,214,141');
      SetLabel(Obj("INFO5"),"Analise operacional atualizada pelo runtime",180,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Notificacoes: indisponiveis • HTTP "+IntegerToString(code),180,361,9,C'255,118,118');
   }
}
void RefreshLearning(){
   string r; int code=0;
   if(Http("GET","/api/learning","",r,code)){
      string progress=JsonValue(r,"progress");
      string active=JsonValue(r,"active_module");
      SetLabel(Obj("INFO1"),"Estudo: "+(active==""?"trilha disponivel":active),180,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Progresso: "+(progress==""?"—":progress),180,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Aprendizado separado da autorizacao operacional.",180,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"learning_authorizes_trading=false",180,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"Historico operacional atualizado",180,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Estudo: runtime indisponivel • HTTP "+IntegerToString(code),180,361,9,C'255,118,118');
   }
}
void RenderView(bool refresh_data=true){
   RefreshNavigation();
   if(active_nav!="N7"){
      for(int i=6;i<=10;i++){
         string extra=Obj("INFO"+IntegerToString(i));
         if(ObjectFind(0,extra)>=0) ObjectDelete(0,extra);
      }
   }
   if(active_view=="COCKPIT"){
      SetLabel(Obj("SUB"),"COCKPIT • motor, decisao, risco, execucao",180,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Motor de decisao: runtime",180,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Risk Gate: atualizando...",180,381,9,C'255,209,102');
      SetLabel(Obj("INFO3"),"Memoria: atualizando...",180,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Estatisticas: atualizando...",180,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Noticias: atualizando...",180,441,9,C'205,215,230');
      SetButton(Obj("ANALYZE"),"ANALISAR NO RUNTIME",180,284,110,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",296,284,114,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",180,320,110,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONC.",296,320,114,28);
      if(refresh_data) RefreshSecondary();
   }else if(active_view=="ANALISE"){
      SetLabel(Obj("SUB"),"ANALISE • leitura produzida pelo runtime, sem valores decorativos",180,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR LEITURA",180,284,110,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",296,284,114,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",180,320,110,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONC.",296,320,114,28);
      if(refresh_data) Analyze();
      SetLabel(Obj("INFO2"),"Risk Gate: "+(runtime_ok?"consultado":"runtime offline"),180,381,9,runtime_ok?C'205,215,230':C'255,118,118');
      SetLabel(Obj("INFO3"),"Fonte da leitura: endpoint /api/runtime/analysis",180,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Candle fechado + filtros: exigidos pelo payload",180,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Sem acao automatica a partir de notificacoes",180,441,9,C'205,215,230');
   }else if(active_view=="MEMORIA"){
      SetLabel(Obj("SUB"),active_nav=="N7"?"WIN/LOSS • resultados, estatisticas e auditoria":"MEMORIA • historico, WIN/LOSS, estatisticas e auditoria",180,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR MEMORIA",180,284,110,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",296,284,114,30);
      SetButton(Obj("SAVE"),"ATUALIZAR ESTAT.",180,320,110,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONC.",296,320,114,28);
      SetLabel(Obj("INFO1"),"Memoria: registros consultados no runtime",180,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Risk Gate: dados reais do runtime",180,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Historico: /api/memory",180,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Estatisticas: /api/statistics",180,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",180,441,9,C'255,155,155');
      // Refresh last so actual runtime statistics are not overwritten by placeholder labels.
      if(refresh_data) RefreshSecondary();
   }else if(active_view=="LAB"){
      SetLabel(Obj("SUB"),"LAB • simulacao, replay e validacao isolados da operacao REAL",180,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"VALIDAR AMBIENTE",180,284,110,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",296,284,114,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",180,320,110,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONC.",296,320,114,28);
      if(refresh_data){ RefreshHealth(); RefreshSecondary(); }
      SetLabel(Obj("INFO1"),"Ambiente: DEMO / SIMULACAO",180,361,9,C'88,214,141');
      SetLabel(Obj("INFO2"),"Risk Gate: somente estado informado pelo runtime",180,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Replay: endpoint nativo ainda nao validado",180,401,9,C'255,209,102');
      SetLabel(Obj("INFO4"),"Execution Gate: controle operacional ativo",180,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Aprendizado separado da operacao",180,441,9,C'205,215,230');
   }else if(active_view=="REPLAY"){
      SetLabel(Obj("SUB"),"REPLAY • ligacao nativa ainda nao confirmada",180,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"VERIFICAR AMBIENTE",180,284,110,30);
      SetLabel(Obj("INFO1"),"Replay nao tem tela nativa ligada neste EA.",180,361,9,C'255,209,102');
      SetLabel(Obj("INFO2"),"Esta tela nao executa nem simula replay.",180,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"A ligacao precisa ser validada no runtime.",180,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Nenhum resultado de replay foi inventado.",180,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",180,441,9,C'255,155,155');
      // Do not leave action buttons from the previous view on this informational screen.
      if(ObjectFind(0,Obj("CYCLE"))>=0) ObjectDelete(0,Obj("CYCLE"));
      if(ObjectFind(0,Obj("CLOSE"))>=0) ObjectDelete(0,Obj("CLOSE"));
      if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
   }else if(active_view=="ALAVANCAGEM"){
      SetLabel(Obj("SUB"),"ALAVANCAGEM • modulo web nao ligado ao EA nativo",180,47,9,C'150,165,185');
      SetLabel(Obj("INFO1"),"Integracao nativa nao confirmada.",180,361,9,C'255,209,102');
      SetLabel(Obj("INFO2"),"Esta tela nao altera alavancagem.",180,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Execucao autorizada: false.",180,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Barreiras operacionais preservadas.",180,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"REAL: BLOQUEADO",180,441,9,C'255,155,155');
      if(ObjectFind(0,Obj("ANALYZE"))>=0) ObjectDelete(0,Obj("ANALYZE"));
      if(ObjectFind(0,Obj("CYCLE"))>=0) ObjectDelete(0,Obj("CYCLE"));
      if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
      if(ObjectFind(0,Obj("CLOSE"))>=0) ObjectDelete(0,Obj("CLOSE"));
   }else if(active_view=="ENSINO"){
      SetLabel(Obj("SUB"),"ESTUDO • aprendizado separado da autorizacao operacional",180,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR ESTUDO",180,284,110,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",296,284,114,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",180,320,110,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONC.",296,320,114,28);
      if(refresh_data) RefreshLearning();
   }else if(active_view=="NOTIF"){
      SetLabel(Obj("SUB"),"NOTIFICACOES • eventos do runtime sem autoridade de execucao",180,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"ATUALIZAR NOTIF.",180,284,110,30);
      SetButton(Obj("CYCLE"),"RODAR CICLO DEMO",296,284,114,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",180,320,110,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONC.",296,320,114,28);
      if(refresh_data) RefreshNotifications();
   }else if(active_view=="CONFIG"){
      SetLabel(Obj("SUB"),"CONFIG • preferencias, seguranca e marca d'agua",180,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"LER CONFIGURACOES",180,284,110,30);
      SetButton(Obj("CYCLE"),watermark_enabled?"MARCA: ON":"MARCA: OFF",296,284,114,30);
      SetButton(Obj("SAVE"),"SALVAR CONFIG",180,320,110,28);
      SetButton(Obj("CLOSE"),"FECHAR + RECONC.",296,320,114,28);
      if(refresh_data) RefreshPreferences();
   }
   if(active_view!="CONFIG" && active_view!="MEMORIA"){
      if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));
   }
   RefreshWatermarkControl();
}
void RefreshHealth(){
   string r; int code=0;
   if(!Http("GET","/api/health","",r,code)){
      runtime_ok=false;
      SetLabel(Obj("RUNTIME"),"Runtime: OFFLINE / HTTP "+IntegerToString(code),180,104,10,C'255,118,118');
      SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • runtime indisponivel",180,520,8,C'255,155,155');
      return;
   }
   runtime_ok=true;
   string mode=JsonValue(r,"mode");
   string real=JsonValue(r,"real");
   string mt5=JsonValue(r,"mt5_demo");
   string exec=JsonValue(r,"execution");
   string engine=JsonValue(r,"decision_engine");
   SetLabel(Obj("RUNTIME"),"Runtime: ONLINE • HTTP "+IntegerToString(code),180,104,10,C'88,214,141');
   SetLabel(Obj("MODE"),"Modo: "+(mode==""?"SIMULACAO":mode)+" • MT5: "+(mt5==""?"DEMO":mt5),180,124,10,C'88,214,141');
   if(active_view=="CONFIG") SetLabel(Obj("SAFE"),"REAL: "+(real==""?"DESABILITADO":real)+" • Execucao: "+(exec==""?"BLOQUEADA":exec),180,520,8,C'255,155,155'); else if(ObjectFind(0,Obj("SAFE"))>=0) ObjectDelete(0,Obj("SAFE"));
   SetLabel(Obj("INFO1"),"Motor de decisao: "+(engine==""?"ONLINE":engine),180,361,9,C'205,215,230');
}
void RefreshMarketAssets(){
   string r; int code=0;
   if(!Http("GET","/api/market/assets","",r,code)){
      SetLabel(Obj("MARKET"),"Ativos/Mercados: indisponiveis • HTTP "+IntegerToString(code),180,278,8,C'255,118,118');
      return;
   }
   // The API returns a top-level count and an assets array; asset entries are not objects with a symbol field.
   string total=JsonValue(r,"count");
   string source=JsonValue(r,"source");
   if(total=="") total="—";
   SetLabel(Obj("MARKET"),"Ativos/Mercados: "+total+" • "+(source==""?"fonte nao informada":source),180,278,8,C'145,160,180');
}
void RefreshSecondary(){
   string r; int code=0;
   if(Http("GET","/api/risk","",r,code)){
      string allowed=JsonValue(r,"allowed");
      string reason=JsonValue(r,"reason");
      SetLabel(Obj("INFO2"),"Risk Gate: "+(allowed=="true"?"PERMITIDO":"BLOQUEADO")+" • "+StringSubstr(reason,0,48),180,381,9,allowed=="true"?C'88,214,141':C'255,209,102');
   }else SetLabel(Obj("INFO2"),"Risk Gate: indisponivel",180,381,9,C'255,118,118');

   if(Http("GET","/api/statistics","",r,code)){
      string total=JsonValue(r,"total");
      string rate=JsonValue(r,"win_rate");
      if(active_nav=="N7"){
         string wins=JsonValue(r,"wins");
         string losses=JsonValue(r,"losses");
         string draws=JsonValue(r,"draws");
         // Estudo usa somente os registros MANUAL_STUDY; não representa P&L.
         string periods=JsonObjectValue(r,"periods");
         string daily=JsonObjectValue(periods,"daily");
         string weekly=JsonObjectValue(periods,"weekly");
         string monthly=JsonObjectValue(periods,"monthly");
         string d_rate=JsonValue(daily,"win_rate");
         string w_rate=JsonValue(weekly,"win_rate");
         string m_rate=JsonValue(monthly,"win_rate");
         string d_closed=IntegerToString((int)StringToInteger(JsonValue(daily,"wins"))+(int)StringToInteger(JsonValue(daily,"losses")));
         string w_closed=IntegerToString((int)StringToInteger(JsonValue(weekly,"wins"))+(int)StringToInteger(JsonValue(weekly,"losses")));
         string m_closed=IntegerToString((int)StringToInteger(JsonValue(monthly,"wins"))+(int)StringToInteger(JsonValue(monthly,"losses")));
         string closed=IntegerToString((int)StringToInteger(wins)+(int)StringToInteger(losses));
         SetLabel(Obj("INFO1"),"Estudo • WIN: "+(wins==""?"—":wins),180,361,9,C'88,214,141');
         SetLabel(Obj("INFO2"),"Estudo • LOSS: "+(losses==""?"—":losses),180,381,9,C'255,118,118');
         SetLabel(Obj("INFO3"),"Estudo • DRAW: "+(draws==""?"—":draws)+" • P&L: nao registrado",180,401,9,C'255,209,102');
         SetLabel(Obj("INFO4"),"Estudo • taxa: "+(closed=="0"?"—":(rate==""?"—":rate)+"%")+" • registros: "+(total==""?"—":total),180,421,9,C'100,235,255');
         SetLabel(Obj("INFO5"),"Estudo • Dia "+(d_closed=="0"?"—":(d_rate==""?"—":d_rate)+"%")+" ("+d_closed+") | Sem "+(w_closed=="0"?"—":(w_rate==""?"—":w_rate)+"%")+" ("+w_closed+") | Mes "+(m_closed=="0"?"—":(m_rate==""?"—":m_rate)+"%")+" ("+m_closed+")",180,441,8,C'100,235,255');

         // DEMO only counts a closed individual position whose MT5 history was reconciled.
         string demo=JsonObjectValue(r,"demo");
         string demo_wins=JsonValue(demo,"wins");
         string demo_losses=JsonValue(demo,"losses");
         string demo_draws=JsonValue(demo,"draws");
         string demo_total=JsonValue(demo,"total");
         string demo_rate=JsonValue(demo,"win_rate");
         string demo_net=JsonValue(demo,"net_result");
         string demo_periods=JsonObjectValue(demo,"periods");
         string demo_daily=JsonObjectValue(demo_periods,"daily");
         string demo_weekly=JsonObjectValue(demo_periods,"weekly");
         string demo_monthly=JsonObjectValue(demo_periods,"monthly");
         string demo_d_rate=JsonValue(demo_daily,"win_rate");
         string demo_w_rate=JsonValue(demo_weekly,"win_rate");
         string demo_m_rate=JsonValue(demo_monthly,"win_rate");
         string demo_d_closed=IntegerToString((int)StringToInteger(JsonValue(demo_daily,"wins"))+(int)StringToInteger(JsonValue(demo_daily,"losses")));
         string demo_w_closed=IntegerToString((int)StringToInteger(JsonValue(demo_weekly,"wins"))+(int)StringToInteger(JsonValue(demo_weekly,"losses")));
         string demo_m_closed=IntegerToString((int)StringToInteger(JsonValue(demo_monthly,"wins"))+(int)StringToInteger(JsonValue(demo_monthly,"losses")));
         SetLabel(Obj("INFO6"),"DEMO • WIN: "+(demo_wins==""?"—":demo_wins),180,461,9,C'88,214,141');
         SetLabel(Obj("INFO7"),"DEMO • LOSS: "+(demo_losses==""?"—":demo_losses),180,481,9,C'255,118,118');
         SetLabel(Obj("INFO8"),"DEMO • DRAW: "+(demo_draws==""?"—":demo_draws)+" • P&L liquido: "+(demo_net==""?"—":demo_net),180,501,9,C'255,209,102');
         SetLabel(Obj("INFO9"),"DEMO • taxa: "+(demo_total=="0"?"—":(demo_rate==""?"—":demo_rate)+"%")+" • fechadas: "+(demo_total==""?"—":demo_total),180,521,9,C'100,235,255');
         SetLabel(Obj("INFO10"),"DEMO • Dia "+(demo_d_closed=="0"?"—":(demo_d_rate==""?"—":demo_d_rate)+"%")+" ("+demo_d_closed+") | Sem "+(demo_w_closed=="0"?"—":(demo_w_rate==""?"—":demo_w_rate)+"%")+" ("+demo_w_closed+") | Mes "+(demo_m_closed=="0"?"—":(demo_m_rate==""?"—":demo_m_rate)+"%")+" ("+demo_m_closed+")",180,541,8,C'100,235,255');
      }else{
         SetLabel(Obj("INFO4"),"Estatisticas: "+(total==""?"—":total)+" decisoes • Win rate "+(rate==""?"—":rate)+"%",180,421,9,C'205,215,230');
      }
   }else SetLabel(Obj("INFO4"),"Estatisticas: indisponiveis",180,421,9,C'255,118,118');

   if(active_nav!="N7"){
      if(Http("GET","/api/news?limit=1","",r,code)){
         string live=JsonValue(r,"live");
         SetLabel(Obj("INFO5"),"Noticias: "+(live=="true"?"ONLINE":"OFFLINE")+" • sem fonte nao interfere na decisao",180,441,9,C'205,215,230');
      }else SetLabel(Obj("INFO5"),"Noticias: indisponiveis",180,441,9,C'255,118,118');
   }

   if(active_nav=="N7"){
      // Outcomes are manual study labels, not broker P&L. Never infer profitability from WIN/LOSS alone.
      SetLabel(Obj("INFO3"),"Rentabilidade: — • P&L financeiro nao registrado",180,401,9,C'255,209,102');
   }else if(Http("GET","/api/memory?limit=1","",r,code)){
      // The endpoint returns a limited records array; it does not promise a total count.
      SetLabel(Obj("INFO3"),"Memoria: resposta recebida do runtime",180,401,9,C'205,215,230');
   }else SetLabel(Obj("INFO3"),"Memoria: indisponivel",180,401,9,C'255,118,118');
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
      SetLabel(Obj("INFO1"),"Configuracoes sincronizadas no runtime • HTTP "+IntegerToString(code),180,361,9,C'88,214,141');
   else
      SetLabel(Obj("INFO1"),"Falha ao sincronizar configuracoes • HTTP "+IntegerToString(code),180,361,9,C'255,118,118');
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
      // A failed analysis invalidates the last analysis health state and all signal quality.
      runtime_ok=false;
      current_signal="AGUARDAR";
      current_quality_score="";
      current_quality_level="";
      RefreshPanelToggle();
      if(render){
         SetLabel(Obj("SIGNAL"),current_signal,180,154,22,C'255,209,102');
         SetLabel(Obj("REASON"),"Analise indisponivel • HTTP "+IntegerToString(code),180,204,9,C'255,118,118');
      }
      return;
   }
   runtime_ok=true;
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   if(signal=="") signal="AGUARDAR";
   current_signal=(signal=="COMPRA" || signal=="COMPRAR")?"COMPRAR":(signal=="VENDA" || signal=="VENDER")?"VENDER":"AGUARDAR";
   string quality=JsonObjectValue(r,"quality");
   string quality_score=JsonValue(quality,"score");
   string quality_level=JsonValue(quality,"level");
   current_quality_score=quality_score;
   current_quality_level=quality_level;
   // Keep the compact C signal current even when the full panel is hidden.
   RefreshPanelToggle();
   if(!render) return;
   string score=JsonValue(r,"score");
   string reason=JsonValue(r,"reason");
   color c=current_signal=="COMPRAR"?C'88,214,141':current_signal=="VENDER"?C'255,118,118':C'255,209,102';
   SetLabel(Obj("SIGNAL"),current_signal,180,154,22,c);
   SetLabel(Obj("SCORE"),"Qualidade: "+(current_quality_score==""?"—":current_quality_score)+"/100 • "+(current_quality_level==""?"—":current_quality_level),180,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Analise concluida pelo runtime.":reason,0,62),180,204,9,C'180,190,205');
   SetLabel(Obj("INFO1"),"Decisao: "+signal+" • score "+(score==""?"—":score)+" • origem runtime",180,361,9,c);
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
   SetLabel(Obj("INFO1"),"Executando ciclo DEMO no runtime...",180,361,9,C'255,209,102');
   if(!Http("POST","/api/runtime/cycle",body,r,code)){
      SetLabel(Obj("INFO1"),"Ciclo bloqueado/falhou • HTTP "+IntegerToString(code),180,361,9,C'255,118,118');
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
   string quality=JsonObjectValue(r,"quality");
   current_quality_score=JsonValue(quality,"score");
   current_quality_level=JsonValue(quality,"level");
   color c=current_signal=="COMPRAR"?C'88,214,141':current_signal=="VENDER"?C'255,86,101':C'255,209,102';
   SetLabel(Obj("SIGNAL"),current_signal,180,154,22,c);
   RefreshPanelToggle();
   SetLabel(Obj("SCORE"),"Qualidade: "+(current_quality_score==""?"—":current_quality_score)+"/100 • "+(current_quality_level==""?"—":current_quality_level),180,184,10,clrWhite);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Ciclo concluido.":reason,0,62),180,204,9,C'180,190,205');
   last_cycle_id=cid; last_external_id=eid;
   SetLabel(Obj("CYCLEID"),"Ciclo: "+(cid==""?"—":cid),180,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execucao: "+(eid==""?"—":eid),180,483,8,C'145,160,180');
   SetLabel(Obj("INFO1"),"Ciclo DEMO: "+signal+" • execucao aceita="+(allowed==""?"false":allowed),180,361,9,allowed=="true"?C'88,214,141':C'255,209,102');
}
void CloseCycle(){
   if(last_cycle_id=="" || last_external_id==""){
      SetLabel(Obj("INFO1"),"Nao ha ciclo DEMO para fechar/reconciliar.",180,361,9,C'255,209,102');
      return;
   }
   string body="{\"cycle_id\":\""+JsonEscape(last_cycle_id)+"\",\"external_id\":\""+JsonEscape(last_external_id)+"\"}";
   string r; int code=0;
   if(Http("POST","/api/runtime/close",body,r,code)){
      string closed=JsonValue(r,"closed");
      if(closed=="true"){
         SetLabel(Obj("INFO1"),"Fechamento DEMO confirmado • reconciliacao solicitada.",180,361,9,C'88,214,141');
         last_cycle_id=""; last_external_id="";
      }else{
         string message=JsonValue(r,"message");
         SetLabel(Obj("INFO1"),"Fechamento nao confirmado: "+StringSubstr(message==""?"runtime nao aceitou a operacao":message,0,42),180,361,9,C'255,118,118');
      }
   }else SetLabel(Obj("INFO1"),"Fechamento falhou/bloqueado • HTTP "+IntegerToString(code),180,361,9,C'255,118,118');
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
   // Keep hidden startup clean: runtime labels belong to the visible panel only.
   // Market analysis may still update the separate signal control without rendering panel labels.
   if(panel_visible){
      RefreshHealth();
      RefreshSecondary();
      RefreshMarketAssets();
   }
   Analyze(panel_visible);
   last_analysis_bar=iTime(_Symbol,_Period,0);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){
   EventKillTimer();
   if(controller_canvas_ready){
      controller_canvas.Destroy();
      controller_canvas_ready=false;
      controller_canvas_size=0;
   }
   DeletePanel();
}
void OnTimer(){
   if(!panel_visible){
      RefreshPanelToggle();
      RefreshWatermarkControl();
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
   if(bid>0) SetLabel(Obj("PRICE"),"Preco atual "+_Symbol+": "+DoubleToString(bid,_Digits),180,501,9,C'190,200,215');
}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   if(id==CHARTEVENT_CHART_CHANGE){
      if(panel_visible){ Panel(); RenderView(false); }
      RefreshPanelToggle();
      RefreshWatermarkControl();
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
   else if(sparam==Obj("CYCLE")) {
      if(active_view=="CONFIG") ToggleWatermark();
      else RunCycle();
   }
   else if(sparam==Obj("SAVE")) {
      if(active_view=="MEMORIA") RefreshSecondary();
      else if(active_view=="CONFIG") SaveConfig();
   }
   else if(sparam==Obj("CLOSE")) CloseCycle();
   // Watermark activation is intentionally available only inside C > Configurações.
}
