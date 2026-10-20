#property strict
#property version   "2.0"
#property description "Controlador Trading - interface nativa do ecossistema no grafico MT5."
#property description "Camada visual e operacional ligada ao runtime; DEMO por padrao."

input string InpRuntimeUrl = "http://127.0.0.1:8000";
input int    InpRefreshSeconds = 3;
input int    InpPanelWidth = 350;
input int    InpPanelHeight = 380;

string P="CTP_";
string last_cycle_id="";
string last_external_id="";
string active_view="COCKPIT";
bool runtime_ok=false;
bool health_ok=false;
bool leverage_enabled=false;
bool leverage_state_known=false;
bool config_fields_dirty=false;
datetime last_analysis_bar=0;
bool panel_visible=false;
bool pref_closed_candle=true;
bool pref_require_filters=true;
int panel_x=0;
int panel_y=18;
int panel_width=350;
int panel_height=380;
double panel_sx=1.0;
double panel_sy=1.0;
bool panel_compact=false;
string last_signal="Aguardar";
string last_score="";

string Obj(string suffix){ return P+suffix; }
string PanelVisibilityKey(){ return P+IntegerToString(ChartID())+"_PANEL_VISIBLE"; }

int SX(int x){ return panel_x+(int)MathRound(x*panel_sx); }
int SidebarWidth(){ return MathMin(142,MathMax(68,(int)MathRound(panel_width*0.34))); }
double ContentScale(){ return (double)MathMax(1,panel_width-SidebarWidth()-16)/430.0; }
int ContentX(int x){ return panel_x+SidebarWidth()+8+(int)MathRound(x*ContentScale()); }
int ContentW(int w){ return MathMax(1,(int)MathRound(w*ContentScale())); }
int ContentY(int y){ return panel_y+50+(int)MathRound(y*((double)MathMax(1,panel_height-62)/540.0)); }
int CompactY(int y){ return (int)MathRound(y*panel_sy); }
int SY(int y){ return panel_y+CompactY(y); }
int SW(int w){ return MathMax(1,(int)MathRound(w*panel_sx)); }
int SH(int h){ return panel_compact?MathMax(21,(int)MathRound(h*panel_sy)):MathMax(1,(int)MathRound(h*panel_sy)); }
void RefreshPanelLayout(){
   int cw=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   // Respect the actual chart bounds, including very small windows. The 66 px bottom reserve keeps native SELL/BUY controls clear.
   panel_width=MathMax(1,MathMin(InpPanelWidth,cw-24));
   panel_x=12;
   panel_y=18;
   int available_height=MathMax(1,ch-panel_y-66);
   int proportional_height=MathMax(1,(int)MathRound(ch*0.48));
   panel_height=MathMax(1,MathMin(InpPanelHeight,MathMin(available_height,proportional_height)));
   panel_sx=(double)panel_width/430.0;
   panel_sy=(double)panel_height/540.0;
   panel_compact=(panel_height<340 || panel_width<350);
   string bg=Obj("BG");
   if(ObjectFind(0,bg)>=0){
      ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,panel_x);
      ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,panel_y);
      ObjectSetInteger(0,bg,OBJPROP_XSIZE,panel_width);
      ObjectSetInteger(0,bg,OBJPROP_YSIZE,panel_height);
   }
}
void SetLabel(string name,string text,int x,int y,int size=10,color clr=clrWhite){
   if(name==Obj("SUB")){
      if(ObjectFind(0,name)>=0) ObjectDelete(0,name);
      return;
   }
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   int px=ContentX(x);
   int py=ContentY(y);
   int fs=MathMax(8,(int)MathRound(size*MathMin(panel_sx,0.92)));
   // Keep compact-panel text inside its area rather than letting long lines spill over the chart.
   bool bounded=(StringFind(name,Obj("INFO"))==0 || name==Obj("REASON") ||
                 name==Obj("MARKET") || name==Obj("SAFE") || name==Obj("PRICE") ||
                 name==Obj("CYCLEID") || name==Obj("EXTID") || name==Obj("LEVERAGE") ||
                 name==Obj("MODE") || name==Obj("RUNTIME") || name==Obj("SYML") || name==Obj("TFL"));
   if(bounded){
      int max_chars=MathMax(14,(int)MathFloor((panel_width-SidebarWidth()-28)/6.2));
      if(StringLen(text)>max_chars) text=StringSubstr(text,0,max_chars-1)+"…";
   }
   if(name==Obj("TITLE")){
      // At narrow widths, prioritize the live signal; the C control already identifies the ecosystem.
      if(panel_width<320) text="";
      px=panel_x+58; py=panel_y+13; fs=(panel_width<390?9:11);
   }else if(name==Obj("SIGNAL")){
      // Keep the signal inside the panel and away from the title at every supported width.
      px=panel_x+(panel_width<320?MathMax(52,panel_width-112):MathMin(218,MathMax(155,panel_width-185))); py=panel_y+10; fs=9;
      string signal_name=SignalLabel(text);
      if(signal_name=="Comprar") text="↑  COMPRAR";
      else if(signal_name=="Vender") text="↓  VENDER";
      else text="AGUARDAR";
   }else if(name==Obj("SCORE")){
      px=panel_x+MathMin(218,MathMax(155,panel_width-185))+10; py=panel_y+26; fs=9;
      if(StringFind(text,"Qualidade:")==0) text="";
   }
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,px);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,py);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,fs);
   ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
   ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void SetButton(string name,string text,int x,int y,int w,int h){
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_BUTTON,0,0,0);
   bool nav=(name==Obj("V1") || name==Obj("V2") || name==Obj("V3") || name==Obj("V4") ||
             name==Obj("V5") || name==Obj("V6") || name==Obj("V7") || name==Obj("V8") ||
             name==Obj("V9") || name==Obj("V10"));
   int button_x=ContentX(x), button_y=ContentY(y), button_w=ContentW(w), button_h=SH(h);
   int button_font=MathMax(8,(int)MathRound(9*MathMin(panel_sx,0.92)));
   int index=0;
   if(name==Obj("V1")) index=1;
   else if(name==Obj("V2")) index=2;
   else if(name==Obj("V3")) index=3;
   else if(name==Obj("V4")) index=4;
   else if(name==Obj("V5")) index=5;
   else if(name==Obj("V6")) index=6;
   else if(name==Obj("V7")) index=7;
   else if(name==Obj("V8")) index=8;
   else if(name==Obj("V9")) index=9;
   else if(name==Obj("V10")) index=10;
   bool selected=false;
   if(index==1 && active_view=="COCKPIT") selected=true;
   if(index==2 && active_view=="ANALISE") selected=true;
   if(index==3 && active_view=="ENSINO") selected=true;
   if(index==4 && active_view=="LAB") selected=true;
   if(index==5 && active_view=="REPLAY") selected=true;
   if(index==6 && active_view=="SIMULADOR") selected=true;
   if(index==7 && active_view=="MEMORIA") selected=true;
   if(index==8 && active_view=="ESTATISTICAS") selected=true;
   if(index==9 && active_view=="CONFIG") selected=true;
   if(index==10 && active_view=="NOTIF") selected=true;
   color button_bg=C'12,25,40';
   color button_border=C'30,65,83';
   if(nav){
      // Fit the ten navigation items while reserving a row for leverage beneath them.
      int nav_area=MathMax(1,panel_height-58);
      int nav_step=MathMax(1,MathMin(25,nav_area/11));
      int row=index;
      // Place leverage beside the study modules; keep Settings and Notifications below it.
      if(index>=9) row=index+1;
      button_x=panel_x+8;
      button_y=panel_y+50+(row-1)*nav_step;
      button_w=MathMax(1,SidebarWidth()-10);
      button_h=MathMax(1,MathMin(22,nav_step-1));
      if(panel_height<180){ button_font=6; }
      else if(panel_height<240){ button_font=7; }
      else { button_font=8; }
      if(selected){ button_bg=C'0,65,83'; button_border=C'0,210,245'; }
   }else if(name==Obj("LEVERAGE_TOGGLE")){
      int nav_area=MathMax(1,panel_height-58);
      int nav_step=MathMax(1,MathMin(25,nav_area/11));
      button_x=panel_x+8;
      button_y=panel_y+50+8*nav_step;
      button_w=MathMax(1,SidebarWidth()-10);
      button_h=MathMax(1,MathMin(22,nav_step-1));
      button_font=(panel_height<240?6:8);
      button_bg=C'12,25,40';
      button_border=C'30,65,83';
   }else{
      button_bg=C'20,38,54';
      button_border=C'48,86,105';
   }
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,button_x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,button_y);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,button_w);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,button_h);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,button_font);
   ObjectSetInteger(0,name,OBJPROP_COLOR,selected?C'0,225,255':clrWhite);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,button_bg);
   ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,button_border);
   ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI Symbol");
   ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}
void SetEdit(string name,string text,int x,int y,int w,int h){
   bool created=(ObjectFind(0,name)<0);
   if(created) ObjectCreate(0,name,OBJ_EDIT,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,ContentX(x));
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,ContentY(y));
   ObjectSetInteger(0,name,OBJPROP_XSIZE,ContentW(w));
   ObjectSetInteger(0,name,OBJPROP_YSIZE,MathMax(22,SH(h)));
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,MathMax(8,(int)MathRound(9*MathMin(panel_sx,0.92))));
   ObjectSetInteger(0,name,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,C'10,14,21');
   ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,C'55,90,112');
   if(created) ObjectSetString(0,name,OBJPROP_TEXT,text);
   ObjectSetInteger(0,name,OBJPROP_READONLY,false);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,true);
   ObjectSetInteger(0,name,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,name,OBJPROP_ZORDER,20);
}
void RefreshPanelToggle(){
   string name=Obj("PANEL_TOGGLE");
   int cw=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int ch=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   int x=MathMax(8,MathMin(12,MathMax(8,cw-54)));
   int y=MathMax(8,MathMin(ch-58,MathMax(8,ch-54)));
   // Dark filled center under the cyan outline: keeps chart grid from showing through the C.
   string fill=Obj("PANEL_TOGGLE_FILL");
   if(ObjectFind(0,fill)<0) ObjectCreate(0,fill,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,fill,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,fill,OBJPROP_XDISTANCE,x+21);
   ObjectSetInteger(0,fill,OBJPROP_YDISTANCE,y+21);
   ObjectSetInteger(0,fill,OBJPROP_FONTSIZE,39);
   ObjectSetInteger(0,fill,OBJPROP_COLOR,C'5,15,27');
   ObjectSetString(0,fill,OBJPROP_FONT,"Segoe UI Symbol");
   ObjectSetString(0,fill,OBJPROP_TEXT,"●");
   ObjectSetInteger(0,fill,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,fill,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,fill,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,fill,OBJPROP_ZORDER,999);
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x+21);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y+21);
   ObjectSetInteger(0,name,OBJPROP_FONTSIZE,43);
   ObjectSetInteger(0,name,OBJPROP_STATE,false);
   ObjectSetInteger(0,name,OBJPROP_COLOR,C'0,215,255');
   ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI Symbol");
   ObjectSetString(0,name,OBJPROP_TEXT,"◯");
   ObjectSetInteger(0,name,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,true);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,name,OBJPROP_ZORDER,1000);
   string letter=Obj("PANEL_TOGGLE_LETTER");
   if(ObjectFind(0,letter)<0) ObjectCreate(0,letter,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,letter,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,letter,OBJPROP_XDISTANCE,x+12);
   ObjectSetInteger(0,letter,OBJPROP_YDISTANCE,y+10);
   ObjectSetInteger(0,letter,OBJPROP_FONTSIZE,20);
   ObjectSetInteger(0,letter,OBJPROP_COLOR,C'0,215,255');
   ObjectSetString(0,letter,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,letter,OBJPROP_TEXT,"C");
   ObjectSetInteger(0,letter,OBJPROP_SELECTABLE,true);
   ObjectSetInteger(0,letter,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,letter,OBJPROP_ZORDER,1001);
   string sig=Obj("COLLAPSED_SIGNAL");
   if(ObjectFind(0,sig)<0) ObjectCreate(0,sig,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,sig,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,sig,OBJPROP_XDISTANCE,62);
   ObjectSetInteger(0,sig,OBJPROP_YDISTANCE,y+3);
   ObjectSetInteger(0,sig,OBJPROP_FONTSIZE,11);
   ObjectSetString(0,sig,OBJPROP_FONT,"Segoe UI");
   string shown_signal=SignalLabel(last_signal);
   string compact_text=(shown_signal=="Comprar"?"↑  COMPRAR":(shown_signal=="Vender"?"↓  VENDER":(shown_signal=="Análise indisponível"?"ANÁLISE INDISPONÍVEL":"AGUARDAR")));
   color compact_color=SignalColor(last_signal);
   ObjectSetInteger(0,sig,OBJPROP_COLOR,compact_color);
   ObjectSetString(0,sig,OBJPROP_TEXT,panel_visible?"":compact_text);
   ObjectSetInteger(0,sig,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,sig,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,sig,OBJPROP_ZORDER,100);
   string quality=Obj("COLLAPSED_QUALITY");
   if(ObjectFind(0,quality)<0) ObjectCreate(0,quality,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,quality,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,quality,OBJPROP_XDISTANCE,94);
   ObjectSetInteger(0,quality,OBJPROP_YDISTANCE,y+22);
   ObjectSetInteger(0,quality,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,quality,OBJPROP_COLOR,compact_color);
   ObjectSetString(0,quality,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,quality,OBJPROP_TEXT,(panel_visible || !IsValidQualityScore(last_score))?"":last_score+"%");
   ObjectSetInteger(0,quality,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,quality,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,quality,OBJPROP_ZORDER,100);
   string close_name=Obj("PANEL_CLOSE");
   if(panel_visible){
      if(ObjectFind(0,close_name)<0) ObjectCreate(0,close_name,OBJ_LABEL,0,0,0);
      ObjectSetInteger(0,close_name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
      ObjectSetInteger(0,close_name,OBJPROP_XDISTANCE,panel_x+panel_width-27);
      ObjectSetInteger(0,close_name,OBJPROP_YDISTANCE,panel_y+5);
      ObjectSetInteger(0,close_name,OBJPROP_FONTSIZE,20);
      ObjectSetInteger(0,close_name,OBJPROP_COLOR,C'0,215,255');
      ObjectSetString(0,close_name,OBJPROP_FONT,"Segoe UI");
      ObjectSetString(0,close_name,OBJPROP_TEXT,"×");
      ObjectSetInteger(0,close_name,OBJPROP_SELECTABLE,true);
      ObjectSetInteger(0,close_name,OBJPROP_HIDDEN,true);
      ObjectSetInteger(0,close_name,OBJPROP_ZORDER,1001);
   }else if(ObjectFind(0,close_name)>=0) ObjectDelete(0,close_name);
}
void TogglePanel(){
   panel_visible=!panel_visible;
   GlobalVariableSet(PanelVisibilityKey(),panel_visible?1.0:0.0);
   if(panel_visible){ Panel(); RenderView(); RefreshHealth(); if(active_view!="CONFIG") RefreshLeveragePreference(); Analyze(true); }
   else DeletePanel(true);
   RefreshPanelToggle();
   ChartRedraw();
}
void LoadPanelVisibility(){
   if(GlobalVariableCheck(PanelVisibilityKey()))
      panel_visible=(GlobalVariableGet(PanelVisibilityKey())>0.5);
   else panel_visible=false;
   RefreshPanelToggle();
}
void Panel(){
   string bg=Obj("BG");
   if(ObjectFind(0,bg)<0) ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   RefreshPanelLayout();
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,panel_x);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,panel_y);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,panel_width);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,panel_height);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,C'8,17,30');
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,C'0,150,190');
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,bg,OBJPROP_ZORDER,0);

   string side=Obj("SIDEBAR_BG");
   if(ObjectFind(0,side)<0) ObjectCreate(0,side,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,side,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,side,OBJPROP_XDISTANCE,panel_x+5);
   ObjectSetInteger(0,side,OBJPROP_YDISTANCE,panel_y+48);
   ObjectSetInteger(0,side,OBJPROP_XSIZE,SidebarWidth());
   ObjectSetInteger(0,side,OBJPROP_YSIZE,MathMax(1,panel_height-57));
   ObjectSetInteger(0,side,OBJPROP_BGCOLOR,C'7,20,34');
   ObjectSetInteger(0,side,OBJPROP_BORDER_COLOR,C'22,62,80');
   ObjectSetInteger(0,side,OBJPROP_BACK,false);
   ObjectSetInteger(0,side,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,side,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,side,OBJPROP_ZORDER,1);

   string content=Obj("CONTENT_BG");
   if(ObjectFind(0,content)<0) ObjectCreate(0,content,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,content,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,content,OBJPROP_XDISTANCE,panel_x+SidebarWidth()+8);
   ObjectSetInteger(0,content,OBJPROP_YDISTANCE,panel_y+48);
   ObjectSetInteger(0,content,OBJPROP_XSIZE,panel_width-SidebarWidth()-16);
   ObjectSetInteger(0,content,OBJPROP_YSIZE,MathMax(1,panel_height-57));
   ObjectSetInteger(0,content,OBJPROP_BGCOLOR,C'5,15,27');
   ObjectSetInteger(0,content,OBJPROP_BORDER_COLOR,C'18,54,72');
   ObjectSetInteger(0,content,OBJPROP_BACK,false);
   ObjectSetInteger(0,content,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,content,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,content,OBJPROP_ZORDER,1);

   SetLabel(Obj("TITLE"),"Controlador Trading",70,27,11,clrWhite);
   SetLabel(Obj("SUB"),"",20,47,9,C'150,165,185');
   SetLabel(Obj("SIGNAL"),last_signal,20,176,10,SignalColor(last_signal));
   SetLabel(Obj("SCORE"),IsValidQualityScore(last_score)?last_score+"%":"",20,206,9,SignalColor(last_signal));

   SetButton(Obj("V1"),"⌂  COCKPIT",18,67,88,25);
   SetButton(Obj("V2"),"⌁  ANÁLISE",110,67,88,25);
   SetButton(Obj("V3"),"▣  ESTUDO",202,67,100,25);
   SetButton(Obj("V4"),"⚗  LABORATÓRIO",18,94,112,25);
   SetButton(Obj("V5"),"◷  REPLAY",134,94,72,25);
   SetButton(Obj("V6"),"◉  SIMULADOR",210,94,100,25);
   SetButton(Obj("V7"),"▤  MEMÓRIA",314,94,106,25);
   SetButton(Obj("V8"),"▥  ESTATÍSTICAS",18,121,112,25);
   SetButton(Obj("V9"),"⚙  CONFIGURAÇÕES",134,121,130,25);
   SetButton(Obj("V10"),"♧  NOTIFICAÇÕES",268,121,130,25);
   SetButton(Obj("LEVERAGE_TOGGLE"),"ALAVANCAGEM: —",190,180,230,25);

   SetLabel(Obj("RUNTIME"),"Sistema indisponível",20,126,10,C'255,118,118');
   SetLabel(Obj("MODE"),"Modo: DEMONSTRAÇÃO / SIMULAÇÃO",20,146,10,C'88,214,141');
   SetLabel(Obj("REASON"),"Aguardando análise.",20,226,9,C'180,190,205');

   SetLabel(Obj("MARKET"),"Ativos e mercados: consultando...",20,300,8,C'145,160,180');

   SetButton(Obj("ANALYZE"),"Analisar no serviço",20,316,172,30);
   SetButton(Obj("CYCLE"),"Executar ciclo de simulação",202,316,177,30);
   SetButton(Obj("SAVE"),"Salvar configurações",20,352,172,28);
   SetButton(Obj("CLOSE"),"Encerrar e reconciliar",202,352,177,28);

   SetLabel(Obj("INFO1"),"Decisão: —",20,361,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Controle de risco: verificando...",20,381,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Memória: verificando...",20,401,9,C'205,215,230');
   SetLabel(Obj("INFO4"),"Estatísticas: verificando...",20,421,9,C'205,215,230');
   SetLabel(Obj("INFO5"),"Notícias: verificando...",20,441,9,C'205,215,230');

   SetLabel(Obj("CYCLEID"),"Ciclo: —",20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execução: —",20,483,8,C'145,160,180');
   SetLabel(Obj("PRICE"),"Preço atual: —",20,501,9,C'190,200,215');
   SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • barreiras mantidas",20,520,8,C'255,155,155');
   RefreshPanelToggle();
}
void DeletePanel(bool preserveToggle=false){
   int total=ObjectsTotal(0,-1,-1);
   for(int i=total-1;i>=0;i--){
      string n=ObjectName(0,i,-1,-1);
      if(StringFind(n,P)!=0) continue;
      if(preserveToggle && (n==Obj("PANEL_TOGGLE") || n==Obj("PANEL_TOGGLE_FILL") || n==Obj("PANEL_TOGGLE_LETTER") || n==Obj("COLLAPSED_SIGNAL") || n==Obj("COLLAPSED_QUALITY"))) continue;
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
string SignalLabel(string signal){
   string normalized=signal;
   StringToUpper(normalized);
   if(normalized=="COMPRA" || normalized=="COMPRAR") return "Comprar";
   if(normalized=="VENDA" || normalized=="VENDER") return "Vender";
   if(normalized=="ANALISE_INDISPONIVEL") return "Análise indisponível";
   return "Aguardar";
}
color SignalColor(string signal){
   string normalized=signal;
   StringToUpper(normalized);
   if(normalized=="COMPRA" || normalized=="COMPRAR") return C'0,255,70';
   if(normalized=="VENDA" || normalized=="VENDER") return C'255,45,65';
   if(normalized=="ANALISE_INDISPONIVEL") return C'255,118,118';
   return C'255,176,0';
}
string NormalizeQualityScore(string raw){
   StringTrimLeft(raw);
   StringTrimRight(raw);
   if(raw=="") return "";
   double value=StringToDouble(raw);
   if(!MathIsValidNumber(value) || value<1.0 || value>100.0) return "";
   int rounded=(int)MathRound(value);
   if(rounded<1 || rounded>100) return "";
   return IntegerToString(rounded);
}
bool IsValidQualityScore(string score){
   if(score=="") return false;
   for(int i=0;i<StringLen(score);i++){
      ushort ch=StringGetCharacter(score,i);
      if(ch<'0' || ch>'9') return false;
   }
   long value=StringToInteger(score);
   return value>=1 && value<=100;
}
string JsonObject(string json,string key){
   string needle="\"" + key + "\":";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   while(p<StringLen(json) && (StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\n' || StringGetCharacter(json,p)=='\r')) p++;
   if(p>=StringLen(json) || StringGetCharacter(json,p)!='{') return "";
   int start=p;
   int depth=0;
   bool in_string=false;
   bool escape_next=false;
   for(int i=p;i<StringLen(json);i++){
      ushort ch=StringGetCharacter(json,i);
      if(in_string){
         if(escape_next) escape_next=false;
         else if(ch=='\\') escape_next=true;
         else if(ch=='"') in_string=false;
         continue;
      }
      if(ch=='"'){ in_string=true; continue; }
      if(ch=='{') depth++;
      else if(ch=='}'){
         depth--;
         if(depth==0) return StringSubstr(json,start,i-start+1);
      }
   }
   return "";
}
string JsonNestedValue(string json,string object_key,string key){
   string object_json=JsonObject(json,object_key);
   if(object_json=="") return "";
   return JsonValue(object_json,key);
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
void RefreshLeveragePreference(){
   string r; int code=0;
   if(!Http("GET","/api/preferences","",r,code)){
      leverage_state_known=false;
      if(ObjectFind(0,Obj("LEVERAGE_TOGGLE"))>=0) SetButton(Obj("LEVERAGE_TOGGLE"),"ALAVANCAGEM: —",190,180,230,25);
      return;
   }
   string value=JsonNestedValue(r,"preferences","leverage_enabled");
   if(value=="") value=JsonValue(r,"leverage_enabled");
   StringToLower(value);
   if(value!="true" && value!="false"){
      leverage_state_known=false;
      if(ObjectFind(0,Obj("LEVERAGE_TOGGLE"))>=0) SetButton(Obj("LEVERAGE_TOGGLE"),"ALAVANCAGEM: —",190,180,230,25);
      return;
   }
   leverage_enabled=(value=="true");
   leverage_state_known=true;
   if(ObjectFind(0,Obj("LEVERAGE_TOGGLE"))>=0) SetButton(Obj("LEVERAGE_TOGGLE"),leverage_enabled?"ALAVANCAGEM: ON":"ALAVANCAGEM: OFF",190,180,230,25);
}
void RefreshPreferences(){
   string r; int code=0;
   if(!Http("GET","/api/preferences","",r,code)){
      leverage_state_known=false;
      SetButton(Obj("LEVERAGE_TOGGLE"),"ALAVANCAGEM: —",190,180,230,25);
      SetLabel(Obj("INFO1"),"Configurações indisponíveis",20,390,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"",20,412,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"",20,434,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"",20,456,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"",20,478,9,C'205,215,230');
      return;
   }
   string mode=JsonNestedValue(r,"preferences","selected_mode");
   string sym=JsonNestedValue(r,"preferences","default_symbol");
   string tf=JsonNestedValue(r,"preferences","default_timeframe");
   string closed=JsonNestedValue(r,"preferences","require_closed_candle");
   string filters=JsonNestedValue(r,"preferences","require_filters");
   string leverage=JsonNestedValue(r,"preferences","leverage_enabled");
   if(mode=="") mode=JsonValue(r,"selected_mode");
   if(sym=="") sym=JsonValue(r,"default_symbol");
   if(tf=="") tf=JsonValue(r,"default_timeframe");
   if(closed=="") closed=JsonValue(r,"require_closed_candle");
   if(filters=="") filters=JsonValue(r,"require_filters");
   if(leverage=="") leverage=JsonValue(r,"leverage_enabled");
   StringToLower(leverage);
   if(leverage=="true" || leverage=="false"){ leverage_enabled=(leverage=="true"); leverage_state_known=true; }
   else leverage_state_known=false;
   SetButton(Obj("LEVERAGE_TOGGLE"),leverage_state_known?(leverage_enabled?"ALAVANCAGEM: ON":"ALAVANCAGEM: OFF"):"ALAVANCAGEM: —",190,180,230,25);
   StringToLower(closed);
   StringToLower(filters);
   if(closed!="") pref_closed_candle=(closed=="true" || closed=="1");
   if(filters!="") pref_require_filters=(filters=="true" || filters=="1");
   SetButton(Obj("ANALYZE"),"Confirmar candle: "+(pref_closed_candle?"Sim":"Não"),20,316,172,30);
   SetButton(Obj("CYCLE"),"Filtros obrigatórios: "+(pref_require_filters?"Sim":"Não"),202,316,177,30);
   if(!config_fields_dirty){
      if(ObjectFind(0,Obj("SYM"))>=0 && sym!="") ObjectSetString(0,Obj("SYM"),OBJPROP_TEXT,sym);
      if(ObjectFind(0,Obj("TF"))>=0 && tf!="") ObjectSetString(0,Obj("TF"),OBJPROP_TEXT,tf);
   }
   SetLabel(Obj("INFO1"),"Modo: "+(mode==""?"DEMO":mode)+" • simbolo: "+(sym==""?"—":sym),20,390,9,C'205,215,230');
   SetLabel(Obj("INFO2"),"Período gráfico: "+(tf==""?"—":tf)+" • confirmação: "+(closed==""?"—":closed),20,412,9,C'205,215,230');
   SetLabel(Obj("INFO3"),"Filtros obrigatórios: "+(filters==""?"—":filters),20,434,9,C'205,215,230');
   SetLabel(Obj("INFO4"),runtime_ok?"Sistema Online":"Serviço indisponível",20,456,9,runtime_ok?C'88,214,141':C'255,118,118');
   SetLabel(Obj("INFO5"),"REAL: bloqueado • preferencias nao concedem autoridade REAL",20,478,9,C'255,155,155');
}
void RefreshNotifications(){
   string r; int code=0;
   if(Http("GET","/api/notifications","",r,code)){
      string unread=JsonValue(r,"unread");
      string total=JsonValue(r,"total");
      SetLabel(Obj("INFO1"),"Notificações: "+(total==""?"resumo recebido":total)+" • nao lidas "+(unread==""?"—":unread),20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Alertas importantes e críticos do ecossistema",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Abra um alerta para conferir os detalhes.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"A análise de mercado é atualizada separadamente.",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"",20,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Notificações indisponíveis",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"",20,441,9,C'205,215,230');
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
      SetLabel(Obj("INFO4"),"Estudo não autoriza operações",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"Historico operacional atualizado",20,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Estudo indisponível",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"",20,441,9,C'205,215,230');
   }
}
void RenderView(){
   // Limpa ações e campos exclusivos da tela anterior para não misturar seções.
   string action_names[3]={Obj("CYCLE"),Obj("SAVE"),Obj("CLOSE")};
   for(int i=0;i<3;i++) if(ObjectFind(0,action_names[i])>=0) ObjectDelete(0,action_names[i]);
   string view_fields[5]={Obj("MARKET"),Obj("PRICE"),Obj("CYCLEID"),Obj("EXTID"),Obj("SAFE")};
   for(int i=0;i<ArraySize(view_fields);i++) if(ObjectFind(0,view_fields[i])>=0) ObjectDelete(0,view_fields[i]);
   if(active_view!="CONFIG"){
      string config_fields[4]={Obj("SYML"),Obj("SYM"),Obj("TFL"),Obj("TF")};
      for(int i=0;i<ArraySize(config_fields);i++) if(ObjectFind(0,config_fields[i])>=0) ObjectDelete(0,config_fields[i]);
   }
   if(active_view!="COCKPIT" && ObjectFind(0,Obj("RUNTIME"))>=0) ObjectDelete(0,Obj("RUNTIME"));
   if(active_view!="COCKPIT" && ObjectFind(0,Obj("MODE"))>=0) ObjectDelete(0,Obj("MODE"));
   if(active_view=="COCKPIT"){
      SetLabel(Obj("SUB"),"Visão geral do ecossistema",20,47,9,C'150,165,185');
      SetLabel(Obj("RUNTIME"),runtime_ok?"Sistema ONLINE":"Sistema INDISPONÍVEL",20,126,10,runtime_ok?C'88,214,141':C'255,118,118');
      SetLabel(Obj("MODE"),"Modo: DEMO / SIMULAÇÃO",20,146,10,C'88,214,141');
      SetLabel(Obj("MARKET"),"Ativos e mercados: consultando...",20,300,8,C'145,160,180');
      SetLabel(Obj("PRICE"),"Preço atual: —",20,501,9,C'190,200,215');
      SetLabel(Obj("INFO1"),"Sistema: "+(runtime_ok?"ONLINE":"INDISPONÍVEL"),20,361,9,runtime_ok?C'88,214,141':C'255,118,118');
      SetLabel(Obj("INFO2"),"",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Execução REAL permanece bloqueada",20,401,9,C'255,155,155');
      SetLabel(Obj("INFO4"),"",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"",20,441,9,C'205,215,230');
      SetButton(Obj("ANALYZE"),"Atualizar análise",20,284,172,30);
   }else if(active_view=="ANALISE"){
      SetLabel(Obj("SUB"),"Análise do mercado",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Atualizar leitura",20,284,172,30);
      Analyze();
      SetLabel(Obj("INFO2"),"Leitura do ecossistema",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Tendência, volume e candle conforme dados disponíveis",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Filtros e contexto da análise",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Alertas não executam operações",20,441,9,C'205,215,230');
   }else if(active_view=="MEMORIA"){
      SetLabel(Obj("SUB"),"Memória • registros e histórico",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Atualizar memória",20,284,172,30);
      RefreshMemory();
   }else if(active_view=="LAB"){
      SetLabel(Obj("SUB"),"Laboratório • simulação e validação",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Validar ambiente",20,284,172,30);
      SetButton(Obj("CYCLE"),"Executar ciclo de simulação",202,284,177,30);
      SetButton(Obj("CLOSE"),"Encerrar e reconciliar",202,320,177,28);
      SetLabel(Obj("INFO1"),"Ambiente de validação",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Simulação separada da operação REAL",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Replay depende de sessão disponível no runtime",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Nenhuma execução REAL é autorizada aqui",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"Confira o resultado retornado pelo serviço",20,441,9,C'205,215,230');
   }else if(active_view=="ENSINO"){
      SetLabel(Obj("SUB"),"Estudo • separado da autorização operacional",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Atualizar estudo",20,284,172,30);
      RefreshLearning();
   }else if(active_view=="REPLAY"){
      SetLabel(Obj("SUB"),"Replay • histórico de sessões",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Verificar runtime",20,284,172,30);
      SetLabel(Obj("INFO1"),"Replay depende de sessão registrada no runtime.",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Nenhuma reprodução é presumida sem sessão.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"O histórico pode ser consultado na Memória.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Execução REAL permanece bloqueada.",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"",20,441,9,C'205,215,230');
   }else if(active_view=="SIMULADOR"){
      SetLabel(Obj("SUB"),"Simulador • apenas DEMO/simulação",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Atualizar análise",20,284,172,30);
      SetButton(Obj("CYCLE"),"Executar ciclo DEMO",202,284,177,30);
      SetButton(Obj("CLOSE"),"Encerrar ciclo",202,320,177,28);
      SetLabel(Obj("INFO1"),"Ciclo enviado ao runtime de simulação.",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Resultados só contam após reconciliação.",20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Estudo não representa lucro financeiro.",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Nenhuma ordem REAL é autorizada aqui.",20,421,9,C'255,155,155');
      SetLabel(Obj("INFO5"),"",20,441,9,C'205,215,230');
   }else if(active_view=="ESTATISTICAS"){
      SetLabel(Obj("SUB"),"Estatísticas • dados do runtime",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Atualizar estatísticas",20,284,172,30);
      RefreshSecondary();
   }else if(active_view=="NOTIF"){
      SetLabel(Obj("SUB"),"Notificações e alertas",20,47,9,C'150,165,185');
      SetButton(Obj("ANALYZE"),"Atualizar notificações",20,284,172,30);
      RefreshNotifications();
   }else if(active_view=="CONFIG"){
      SetLabel(Obj("SUB"),"Configurações do ecossistema",20,47,9,C'150,165,185');
      SetLabel(Obj("RUNTIME"),runtime_ok?"Sistema ONLINE":"Sistema INDISPONÍVEL",20,126,10,runtime_ok?C'88,214,141':C'255,118,118');
      SetLabel(Obj("MODE"),"Modo: DEMO / SIMULAÇÃO",20,146,10,C'88,214,141');
      if(ObjectFind(0,Obj("SYML"))<0) SetLabel(Obj("SYML"),"Ativo",20,258,8,C'130,145,165');
      if(ObjectFind(0,Obj("SYM"))<0) SetEdit(Obj("SYM"),_Symbol,20,271,150,25);
      if(ObjectFind(0,Obj("TFL"))<0) SetLabel(Obj("TFL"),"Período gráfico",184,258,8,C'130,145,165');
      if(ObjectFind(0,Obj("TF"))<0) SetEdit(Obj("TF"),NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period)),184,271,195,25);
      SetButton(Obj("ANALYZE"),"Confirmar candle: "+(pref_closed_candle?"Sim":"Não"),20,316,172,30);
      SetButton(Obj("CYCLE"),"Filtros obrigatórios: "+(pref_require_filters?"Sim":"Não"),202,316,177,30);
      SetButton(Obj("SAVE"),"Salvar configurações",20,352,172,28);
      RefreshPreferences();
   }
}
void RefreshHealth(){
   string r; int code=0;
   if(!Http("GET","/api/health","",r,code)){
      runtime_ok=false; health_ok=false;
      last_signal="ANALISE_INDISPONIVEL"; last_score="";
      RefreshPanelToggle();
      if(panel_visible && (active_view=="COCKPIT" || active_view=="CONFIG"))
         SetLabel(Obj("RUNTIME"),"Sistema INDISPONÍVEL",20,126,10,C'255,118,118');
      else if(ObjectFind(0,Obj("RUNTIME"))>=0) ObjectDelete(0,Obj("RUNTIME"));
      if(panel_visible && active_view=="CONFIG")
         SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • runtime indisponivel",20,520,8,C'255,155,155');
      else if(ObjectFind(0,Obj("SAFE"))>=0) ObjectDelete(0,Obj("SAFE"));
      if(!panel_visible && ObjectFind(0,Obj("MODE"))>=0) ObjectDelete(0,Obj("MODE"));
      return;
   }
   string health=JsonValue(r,"health");
   string ok=JsonValue(r,"ok");
   string mode=JsonValue(r,"mode");
   string real=JsonValue(r,"real");
   string mt5=JsonValue(r,"mt5_demo");
   string engine=JsonValue(r,"decision_engine");
   string execution_allowed=JsonValue(r,"execution_allowed");
   StringToUpper(health); StringToUpper(mode); StringToUpper(real);
   StringToUpper(mt5); StringToUpper(engine); StringToLower(execution_allowed);
   bool health_level_ok=(health=="OK" || health=="WARNING");
   health_ok=(ok=="true" && health_level_ok && mode=="SIMULACAO" && engine=="ONLINE" && execution_allowed=="false" && real=="DESABILITADO" && mt5=="DEMO_VALIDADO");
   runtime_ok=health_ok;
   if(!health_ok){
      last_signal="ANALISE_INDISPONIVEL"; last_score="";
      RefreshPanelToggle();
   }
   if(panel_visible && (active_view=="COCKPIT" || active_view=="CONFIG")){
      SetLabel(Obj("RUNTIME"),runtime_ok?"Sistema ONLINE":"Sistema INDISPONÍVEL",20,126,10,runtime_ok?C'88,214,141':C'255,118,118');
      SetLabel(Obj("MODE"),"Modo: "+(mode==""?"SIMULACAO":mode)+" • MT5: "+(mt5==""?"DEMO":mt5),20,146,10,runtime_ok?C'88,214,141':C'255,118,118');
   }else{
      if(ObjectFind(0,Obj("RUNTIME"))>=0) ObjectDelete(0,Obj("RUNTIME"));
      if(ObjectFind(0,Obj("MODE"))>=0) ObjectDelete(0,Obj("MODE"));
   }
   if(panel_visible && active_view=="CONFIG") SetLabel(Obj("SAFE"),"REAL: BLOQUEADO • execução REAL desabilitada",20,520,8,C'255,155,155');
   else if(ObjectFind(0,Obj("SAFE"))>=0) ObjectDelete(0,Obj("SAFE"));
}
void RefreshMarketAssets(){
   string r; int code=0;
   if(!Http("GET","/api/market/assets","",r,code)){
      SetLabel(Obj("MARKET"),"Dados de mercado indisponíveis",20,278,8,C'255,118,118');
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
   SetLabel(Obj("MARKET"),"Ativos/mercados: "+IntegerToString(total)+" • "+(source==""?"MT5 DEMO":source),20,278,8,C'145,160,180');
}
void RefreshSecondary(){
   string r; int code=0;
   if(Http("GET","/api/risk","",r,code)){
      string allowed=JsonValue(r,"allowed");
      string reason=JsonValue(r,"reason");
      SetLabel(Obj("INFO2"),"Controle de risco: "+(allowed=="true"?"PERMITIDO":"BLOQUEADO")+" • "+StringSubstr(reason,0,48),20,381,9,allowed=="true"?C'88,214,141':C'255,209,102');
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
void RefreshMemory(){
   string r; int code=0;
   if(Http("GET","/api/memory?limit=20","",r,code)){
      // The API returns {"records":[...]}; it does not promise total/count fields.
      int returned=0;
      int cursor=0;
      while(true){
         int hit=StringFind(r,"\"decision_id\":",cursor);
         if(hit<0) break;
         returned++;
         cursor=hit+14;
         if(returned>=20) break;
      }
      SetLabel(Obj("INFO1"),"Memória consultada no runtime",20,361,9,C'205,215,230');
      SetLabel(Obj("INFO2"),"Registros nesta consulta: "+IntegerToString(returned),20,381,9,C'205,215,230');
      SetLabel(Obj("INFO3"),"Estudo e simulação não são lucro financeiro",20,401,9,C'205,215,230');
      SetLabel(Obj("INFO4"),"Resultados financeiros exigem confirmação",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Histórico financeiro não confirmado não é tratado como WIN/LOSS",20,441,9,C'205,215,230');
   }else{
      SetLabel(Obj("INFO1"),"Memória indisponível",20,361,9,C'255,118,118');
      SetLabel(Obj("INFO2"),"Não foi possível consultar registros.",20,381,9,C'255,118,118');
      SetLabel(Obj("INFO3"),"Nenhum dado anterior é apresentado como atualização.",20,401,9,C'255,118,118');
      SetLabel(Obj("INFO4"),"Estatísticas não são exibidas nesta seção.",20,421,9,C'205,215,230');
      SetLabel(Obj("INFO5"),"Verifique o serviço e tente atualizar novamente.",20,441,9,C'255,118,118');
   }
}
void SaveConfig(){
   if(!leverage_state_known){
      RefreshLeveragePreference();
      if(!leverage_state_known){
         SetLabel(Obj("INFO1"),"Preferência indisponível; configuração não alterada",20,(active_view=="CONFIG"?390:361),9,C'255,118,118');
         return;
      }
   }
   // Read current preferences first so a leverage toggle outside Settings cannot overwrite symbol/timeframe or filters.
   bool requested_leverage=leverage_enabled;
   string r; int code=0;
   int status_y=(active_view=="CONFIG"?390:361);
   if(!Http("GET","/api/preferences","",r,code)){
      SetLabel(Obj("INFO1"),"Runtime indisponível; configuração não alterada",20,status_y,9,C'255,118,118');
      leverage_state_known=false;
      SetButton(Obj("LEVERAGE_TOGGLE"),"ALAVANCAGEM: —",190,180,230,25);
      return;
   }
   string saved_sym=JsonNestedValue(r,"preferences","default_symbol");
   string saved_tf=JsonNestedValue(r,"preferences","default_timeframe");
   string saved_closed=JsonNestedValue(r,"preferences","require_closed_candle");
   string saved_filters=JsonNestedValue(r,"preferences","require_filters");
   if(saved_sym=="") saved_sym=JsonValue(r,"default_symbol");
   if(saved_tf=="") saved_tf=JsonValue(r,"default_timeframe");
   if(saved_closed=="") saved_closed=JsonValue(r,"require_closed_candle");
   if(saved_filters=="") saved_filters=JsonValue(r,"require_filters");
   StringToLower(saved_closed);
   StringToLower(saved_filters);
   bool closed_known=(saved_closed=="true" || saved_closed=="false" || saved_closed=="1" || saved_closed=="0");
   bool filters_known=(saved_filters=="true" || saved_filters=="false" || saved_filters=="1" || saved_filters=="0");
   if(!closed_known || !filters_known){
      SetLabel(Obj("INFO1"),"Preferências incompletas; configuração não alterada",20,status_y,9,C'255,118,118');
      return;
   }
   string sym=saved_sym;
   string tf=saved_tf;
   bool requested_closed=(saved_closed=="true" || saved_closed=="1");
   bool requested_filters=(saved_filters=="true" || saved_filters=="1");
   if(active_view=="CONFIG"){
      if(ObjectFind(0,Obj("SYM"))>=0){
         string edited_sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
         if(edited_sym!="") sym=edited_sym;
      }
      if(ObjectFind(0,Obj("TF"))>=0){
         string edited_tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
         if(edited_tf!="") tf=edited_tf;
      }
      requested_closed=pref_closed_candle;
      requested_filters=pref_require_filters;
   }
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   tf=NormalizeTimeframe(tf);
   string requested_sym=sym;
   string requested_tf=tf;
   string body="{\"selected_mode\":\"DEMO\",\"leverage_enabled\":"+(requested_leverage?"true":"false")+",\"default_symbol\":\""+JsonEscape(sym)+"\",\"default_timeframe\":\""+JsonEscape(tf)+"\",\"require_closed_candle\":"+(requested_closed?"true":"false")+",\"require_filters\":"+(requested_filters?"true":"false")+"}";
   if(!Http("POST","/api/preferences",body,r,code)){
      SetLabel(Obj("INFO1"),"Não foi possível sincronizar configurações",20,status_y,9,C'255,118,118');
      RefreshLeveragePreference();
      return;
   }
   // Confirm persistence by reading back every preference sent, not just HTTP 2xx.
   if(!Http("GET","/api/preferences","",r,code)){
      leverage_state_known=false;
      SetButton(Obj("LEVERAGE_TOGGLE"),"ALAVANCAGEM: —",190,180,230,25);
      SetLabel(Obj("INFO1"),"Salvo sem confirmação de leitura; runtime indisponível",20,status_y,9,C'255,118,118');
      return;
   }
   string mode=JsonNestedValue(r,"preferences","selected_mode");
   saved_sym=JsonNestedValue(r,"preferences","default_symbol");
   saved_tf=JsonNestedValue(r,"preferences","default_timeframe");
   saved_closed=JsonNestedValue(r,"preferences","require_closed_candle");
   saved_filters=JsonNestedValue(r,"preferences","require_filters");
   string saved_leverage=JsonNestedValue(r,"preferences","leverage_enabled");
   if(mode=="") mode=JsonValue(r,"selected_mode");
   if(saved_sym=="") saved_sym=JsonValue(r,"default_symbol");
   if(saved_tf=="") saved_tf=JsonValue(r,"default_timeframe");
   if(saved_closed=="") saved_closed=JsonValue(r,"require_closed_candle");
   if(saved_filters=="") saved_filters=JsonValue(r,"require_filters");
   if(saved_leverage=="") saved_leverage=JsonValue(r,"leverage_enabled");
   StringToUpper(mode);
   StringToLower(saved_closed);
   StringToLower(saved_filters);
   StringToLower(saved_leverage);
   closed_known=(saved_closed=="true" || saved_closed=="false" || saved_closed=="1" || saved_closed=="0");
   filters_known=(saved_filters=="true" || saved_filters=="false" || saved_filters=="1" || saved_filters=="0");
   bool leverage_known=(saved_leverage=="true" || saved_leverage=="false");
   bool saved_closed_value=(saved_closed=="true" || saved_closed=="1");
   bool saved_filters_value=(saved_filters=="true" || saved_filters=="1");
   bool saved_leverage_value=(saved_leverage=="true");
   bool readback_ok=(mode=="DEMO" && saved_sym==requested_sym &&
      NormalizeTimeframe(saved_tf)==requested_tf &&
      closed_known && saved_closed_value==requested_closed &&
      filters_known && saved_filters_value==requested_filters &&
      leverage_known && saved_leverage_value==requested_leverage);
   if(leverage_known){
      leverage_enabled=saved_leverage_value;
      leverage_state_known=true;
   }else leverage_state_known=false;
   SetButton(Obj("LEVERAGE_TOGGLE"),leverage_state_known?(leverage_enabled?"ALAVANCAGEM: ON":"ALAVANCAGEM: OFF"):"ALAVANCAGEM: —",190,180,230,25);
   if(readback_ok){
      if(active_view=="CONFIG"){
         config_fields_dirty=false;
         RefreshPreferences();
      }
      SetLabel(Obj("INFO1"),"Configurações confirmadas pelo runtime",20,status_y,9,C'88,214,141');
   }else{
      SetLabel(Obj("INFO1"),"Configurações não confirmadas; confira o runtime",20,status_y,9,C'255,118,118');
   }
}
void Analyze(bool render=true){
   RefreshHealth();
   if(!health_ok){
      last_signal="ANALISE_INDISPONIVEL"; last_score=""; RefreshPanelToggle();
      if(render){ SetLabel(Obj("SIGNAL"),"AGUARDAR",20,176,10,C'255,176,0'); SetLabel(Obj("SCORE"),"",20,206,9,clrWhite); SetLabel(Obj("REASON"),"Sistema indisponível; sinal descartado",20,226,9,C'255,118,118'); }
      return;
   }
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
   string body="{\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"limit\":100,\"confirmed\":"+(pref_closed_candle?"true":"false")+",\"filters_ok\":"+(pref_require_filters?"true":"false")+"}";
   string r; int code=0;
   if(!Http("POST","/api/runtime/analysis",body,r,code)){
      last_signal="ANALISE_INDISPONIVEL";
      last_score="";
      RefreshPanelToggle();
      if(render){
         SetLabel(Obj("SIGNAL"),"Análise indisponível",20,176,10,C'255,118,118');
         SetLabel(Obj("SCORE"),"",20,206,9,clrWhite);
         SetLabel(Obj("REASON"),"Falha no runtime; sinal anterior descartado",20,226,9,C'255,118,118');
      }
      return;
   }
   string signal=JsonValue(r,"signal");
   if(signal=="") signal=JsonValue(r,"decision");
   StringToUpper(signal);
   if(signal=="") signal="AGUARDAR";
   string score=NormalizeQualityScore(JsonNestedValue(r,"quality","score"));
   string reason=JsonValue(r,"reason");
   bool quality_valid=IsValidQualityScore(score);
   if(!quality_valid){ signal="ANALISE_INDISPONIVEL"; score=""; reason="Qualidade indisponível; análise não pode ser apresentada com segurança."; }
   last_signal=signal;
   last_score=score;
   RefreshPanelToggle();
   if(!render) return;
   color c=SignalColor(signal);
   SetLabel(Obj("SIGNAL"),SignalLabel(signal),20,176,10,c);
   SetLabel(Obj("SCORE"),score==""?"":score+"%",20,206,9,c);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Análise concluída pelo runtime.":reason,0,62),20,226,9,C'180,190,205');
   // Keep the compact market signal in the chart header; show analysis detail only on the Analysis tab.
   if(active_view=="ANALISE")
      SetLabel(Obj("INFO1"),"Decisão: "+SignalLabel(signal)+" • qualidade "+(score==""?"—":score)+" • origem runtime",20,361,9,c);
   ChartRedraw();
}
void RunCycle(){
   RefreshHealth();
   if(!health_ok){
      last_signal="ANALISE_INDISPONIVEL"; last_score=""; last_cycle_id=""; last_external_id=""; RefreshPanelToggle();
      SetLabel(Obj("INFO1"),"Sistema indisponível; ciclo bloqueado",20,361,9,C'255,118,118');
      SetLabel(Obj("SIGNAL"),"AGUARDAR",20,176,10,C'255,176,0'); SetLabel(Obj("SCORE"),"",20,206,9,clrWhite);
      SetLabel(Obj("REASON"),"Runtime/segurança não confirmados",20,226,9,C'255,118,118');
      return;
   }
   string sym=ObjectGetString(0,Obj("SYM"),OBJPROP_TEXT);
   string tf=ObjectGetString(0,Obj("TF"),OBJPROP_TEXT);
   if(sym=="") sym=_Symbol;
   if(tf=="") tf=NormalizeTimeframe(EnumToString((ENUM_TIMEFRAMES)_Period));
   tf=NormalizeTimeframe(tf);
   string body="{\"symbol\":\""+JsonEscape(sym)+"\",\"timeframe\":\""+JsonEscape(tf)+"\",\"limit\":100,\"amount\":0.01,\"duration_seconds\":60,\"confirmed\":"+(pref_closed_candle?"true":"false")+",\"filters_ok\":"+(pref_require_filters?"true":"false")+",\"entry_conditions\":[]}";
   string r; int code=0;
   SetLabel(Obj("INFO1"),"Executando ciclo de demonstração no runtime...",20,361,9,C'255,209,102');
   if(!Http("POST","/api/runtime/cycle",body,r,code)){
      last_signal="ANALISE_INDISPONIVEL";
      last_score="";
      last_cycle_id="";
      last_external_id="";
      RefreshPanelToggle();
      SetLabel(Obj("SIGNAL"),"Análise indisponível",20,176,10,C'255,118,118');
      SetLabel(Obj("SCORE"),"",20,206,9,clrWhite);
      SetLabel(Obj("REASON"),"Ciclo não confirmado; sinal anterior descartado.",20,226,9,C'255,118,118');
      SetLabel(Obj("CYCLEID"),"Ciclo: não confirmado",20,391,8,C'255,118,118');
      SetLabel(Obj("EXTID"),"Execução: não confirmada",20,406,8,C'255,118,118');
      SetLabel(Obj("INFO1"),"Ciclo indisponível; runtime não confirmou resultado",20,361,9,C'255,118,118');
      return;
   }
   string runtime=JsonObject(r,"runtime");
   if(runtime==""){
      last_signal="ANALISE_INDISPONIVEL";
      last_score="";
      last_cycle_id="";
      last_external_id="";
      RefreshPanelToggle();
      SetLabel(Obj("SIGNAL"),"Análise indisponível",20,176,10,C'255,118,118');
      SetLabel(Obj("SCORE"),"",20,206,9,clrWhite);
      SetLabel(Obj("REASON"),"Resposta do runtime inválida; sinal descartado.",20,226,9,C'255,118,118');
      SetLabel(Obj("CYCLEID"),"Ciclo: não confirmado",20,391,8,C'255,118,118');
      SetLabel(Obj("EXTID"),"Execução: não confirmada",20,406,8,C'255,118,118');
      SetLabel(Obj("INFO1"),"Resposta do ciclo inválida",20,361,9,C'255,118,118');
      return;
   }
   string signal=JsonValue(runtime,"signal");
   if(signal=="") signal=JsonValue(runtime,"decision");
   StringToUpper(signal);
   if(signal=="") signal="AGUARDAR";
   string score=NormalizeQualityScore(JsonNestedValue(runtime,"quality","score"));
   string reason=JsonValue(runtime,"reason");
   bool quality_valid=IsValidQualityScore(score);
   if(!quality_valid){ signal="ANALISE_INDISPONIVEL"; score=""; reason="Qualidade indisponível; análise não pode ser apresentada com segurança."; }
   string cid=JsonValue(runtime,"cycle_id");
   string eid=JsonValue(runtime,"external_id");
   string allowed=JsonValue(r,"execution_allowed");
   color c=SignalColor(signal);
   SetLabel(Obj("SIGNAL"),SignalLabel(signal),20,176,10,c);
   SetLabel(Obj("SCORE"),score==""?"":score+"%",20,206,9,c);
   SetLabel(Obj("REASON"),StringSubstr(reason==""?"Ciclo concluído.":reason,0,62),20,226,9,C'180,190,205');
   last_signal=signal; last_score=score; RefreshPanelToggle();
   last_cycle_id=cid; last_external_id=eid;
   SetLabel(Obj("CYCLEID"),"Ciclo: "+(cid==""?"—":cid),20,465,8,C'145,160,180');
   SetLabel(Obj("EXTID"),"Execução: "+(eid==""?"—":eid),20,483,8,C'145,160,180');
   if(!quality_valid){
      SetLabel(Obj("INFO1"),"Análise indisponível; resultado do ciclo precisa ser confirmado",20,361,9,C'255,176,0');
   }else{
      SetLabel(Obj("INFO1"),"Ciclo de demonstração: "+SignalLabel(signal)+" • autorizado="+(allowed==""?"false":allowed),20,361,9,allowed=="true"?C'88,214,141':C'255,176,0');
   }
}
void CloseCycle(){
   if(last_cycle_id=="" || last_external_id==""){
      SetLabel(Obj("INFO1"),"Não há ciclo de demonstração para fechar ou reconciliar.",20,361,9,C'255,209,102');
      return;
   }
   string body="{\"cycle_id\":\""+JsonEscape(last_cycle_id)+"\",\"external_id\":\""+JsonEscape(last_external_id)+"\"}";
   string r; int code=0;
   if(!Http("POST","/api/runtime/close",body,r,code)){
      SetLabel(Obj("INFO1"),"Fechamento falhou ou foi bloqueado",20,361,9,C'255,118,118');
      return;
   }
   string closed=JsonValue(r,"closed");
   string reconciliation=JsonValue(r,"reconciliation");
   // Runtime reconciliation confirms terminal execution state separately from outcome certainty.
   // UNVERIFIED is expected for financial outcome when no external outcome observation exists.
   string terminal_state=JsonValue(r,"terminal_state");
   StringToUpper(terminal_state);
   bool has_reconciliation=(reconciliation!="" && reconciliation!="null" && StringSubstr(reconciliation,0,1)=="{");
   bool reconciled=(has_reconciliation && (terminal_state=="COMPLETED" || terminal_state=="BLOCKED"));
   string outcome_state=JsonValue(r,"reconciliation_state");
   StringToUpper(outcome_state);
   if(closed=="true" && reconciled){
      string suffix=(outcome_state=="UNVERIFIED"?" Resultado financeiro ainda não verificado.":"");
      SetLabel(Obj("INFO1"),"Fechamento e estado da execução reconciliados."+suffix,20,361,9,C'88,214,141');
      last_cycle_id=""; last_external_id="";
   }else if(closed=="true"){
      SetLabel(Obj("INFO1"),"Fechamento aceito; estado terminal ainda não confirmado.",20,361,9,C'255,176,0');
   }else{
      string message=JsonValue(r,"message");
      SetLabel(Obj("INFO1"),"Fechamento não confirmado: "+StringSubstr(message==""?"runtime não confirmou":message,0,44),20,361,9,C'255,118,118');
   }
}
int OnInit(){
   // Clean any stale CTP visual objects left by a prior EA build on this chart.
   DeletePanel();
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
   RefreshMarketAssets();
   // Prime runtime market-data state immediately, even when the native panel is hidden.
   Analyze(panel_visible);
   last_analysis_bar=iTime(_Symbol,_Period,0);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){
   // Persist only the user-controlled visibility state before the EA is unloaded.
   // Runtime refreshes, chart changes and analysis must never decide to close the panel.
   GlobalVariableSet(PanelVisibilityKey(),panel_visible?1.0:0.0);
   EventKillTimer();
   DeletePanel();
   ChartRedraw();
}
void OnTimer(){
   RefreshHealth();
   if(!panel_visible){
      RefreshPanelToggle();
      datetime hidden_bar=iTime(_Symbol,_Period,0);
      if(hidden_bar>0 && hidden_bar!=last_analysis_bar){
         last_analysis_bar=hidden_bar;
         Analyze(false);
      }
      return;
   }
   RefreshPanelLayout();
   RefreshPanelToggle();
   // CONFIG reads leverage_enabled in RefreshPreferences; avoid a duplicate GET on every timer tick.
   if(active_view=="CONFIG") RefreshPreferences();
   else RefreshLeveragePreference();
   if(active_view=="COCKPIT") { RefreshMarketAssets(); }
   else if(active_view=="NOTIF") RefreshNotifications();
   datetime current_bar=iTime(_Symbol,_Period,0);
   if(current_bar>0 && current_bar!=last_analysis_bar){
      last_analysis_bar=current_bar;
      // Refresh from broker once per new chart bar, not every timer tick.
      Analyze(active_view=="COCKPIT" || active_view=="ANALISE");
   }
   if(active_view=="COCKPIT"){
      double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
      if(bid>0) SetLabel(Obj("PRICE"),"Preço atual "+_Symbol+": "+DoubleToString(bid,_Digits),20,501,9,C'190,200,215');
   }
}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam){
   // Rebuild every panel control after chart resize so the background and controls keep the same geometry.
   if(id==CHARTEVENT_CHART_CHANGE){
      if(panel_visible){ Panel(); RenderView(); RefreshPanelToggle(); ChartRedraw(); }
      else RefreshPanelToggle();
      return;
   }
   if(id==CHARTEVENT_OBJECT_ENDEDIT && (sparam==Obj("SYM") || sparam==Obj("TF"))){
      config_fields_dirty=true;
      return;
   }
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   if(sparam==Obj("PANEL_TOGGLE") || sparam==Obj("PANEL_TOGGLE_LETTER")) { TogglePanel(); return; }
   if(sparam==Obj("PANEL_CLOSE")) { TogglePanel(); return; }
   if(sparam==Obj("V1")) { active_view="COCKPIT"; RenderView(); }
   else if(sparam==Obj("V2")) { active_view="ANALISE"; RenderView(); }
   else if(sparam==Obj("V3")) { active_view="ENSINO"; RenderView(); }
   else if(sparam==Obj("V4")) { active_view="LAB"; RenderView(); }
   else if(sparam==Obj("V5")) { active_view="REPLAY"; RenderView(); }
   else if(sparam==Obj("V6")) { active_view="SIMULADOR"; RenderView(); }
   else if(sparam==Obj("V7")) { active_view="MEMORIA"; RenderView(); }
   else if(sparam==Obj("V8")) { active_view="ESTATISTICAS"; RenderView(); }
   else if(sparam==Obj("V9")) { active_view="CONFIG"; config_fields_dirty=false; RenderView(); }
   else if(sparam==Obj("V10")) { active_view="NOTIF"; RenderView(); }
   else if(sparam==Obj("ANALYZE")) {
      if(active_view=="REPLAY") RefreshHealth();
      else if(active_view=="ESTATISTICAS") RefreshSecondary();
      else if(active_view=="CONFIG"){ pref_closed_candle=!pref_closed_candle; SetButton(Obj("ANALYZE"),"Confirmar candle: "+(pref_closed_candle?"Sim":"Não"),20,316,172,30); SaveConfig(); }
      else if(active_view=="ANALISE") Analyze();
      else if(active_view=="MEMORIA") RefreshMemory();
      else if(active_view=="LAB") RefreshHealth();
      else if(active_view=="ENSINO") RefreshLearning();
      else if(active_view=="NOTIF") RefreshNotifications();
      else Analyze();
   }
   else if(sparam==Obj("CYCLE")) { if(active_view=="CONFIG"){ pref_require_filters=!pref_require_filters; SetButton(Obj("CYCLE"),"Filtros obrigatórios: "+(pref_require_filters?"Sim":"Não"),202,316,177,30); SaveConfig(); } else RunCycle(); }
   else if(sparam==Obj("SAVE")) SaveConfig();
   else if(sparam==Obj("LEVERAGE_TOGGLE")) {
      if(!leverage_state_known) RefreshLeveragePreference();
      if(!leverage_state_known){ SetButton(Obj("LEVERAGE_TOGGLE"),"ALAVANCAGEM: —",190,180,230,25); return; }
      leverage_enabled=!leverage_enabled;
      SaveConfig();
   }
   else if(sparam==Obj("CLOSE")) CloseCycle();
}