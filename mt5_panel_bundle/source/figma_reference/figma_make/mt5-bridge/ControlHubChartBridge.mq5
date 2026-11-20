#property strict
#property version   "1.00"
#property description "Ponte somente de leitura: publica simbolo e periodo deste grafico para o Control Hub. Nao envia ordens."

input int PublicarACadaSegundos = 1;

string PeriodoTexto(const ENUM_TIMEFRAMES periodo)
{
   switch(periodo)
   {
      case PERIOD_M1: return "1m";
      case PERIOD_M2: return "2m";
      case PERIOD_M3: return "3m";
      case PERIOD_M4: return "4m";
      case PERIOD_M5: return "5m";
      case PERIOD_M6: return "6m";
      case PERIOD_M10: return "10m";
      case PERIOD_M12: return "12m";
      case PERIOD_M15: return "15m";
      case PERIOD_M20: return "20m";
      case PERIOD_M30: return "30m";
      case PERIOD_H1: return "1h";
      case PERIOD_H2: return "2h";
      case PERIOD_H3: return "3h";
      case PERIOD_H4: return "4h";
      case PERIOD_H6: return "6h";
      case PERIOD_H8: return "8h";
      case PERIOD_H12: return "12h";
      case PERIOD_D1: return "1d";
      case PERIOD_W1: return "1w";
      case PERIOD_MN1: return "1mo";
      default: return IntegerToString(PeriodSeconds(periodo)/60)+"m";
   }
}

void PublicarContexto()
{
   FolderCreate("ControlHub", FILE_COMMON);
   int arquivo=FileOpen("ControlHub\\active_chart.json", FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
   if(arquivo==INVALID_HANDLE) return;
   string simbolo=_Symbol;
   StringReplace(simbolo, "\\", "\\\\");
   StringReplace(simbolo, "\"", "\\\"");
   string json="{\"symbol\":\""+simbolo+"\",\"timeframe\":\""+PeriodoTexto((ENUM_TIMEFRAMES)_Period)+"\",\"chart_id\":"+IntegerToString(ChartID())+"}";
   FileWriteString(arquivo,json);
   FileClose(arquivo);
}

int OnInit()
{
   int intervalo=PublicarACadaSegundos;
   if(intervalo<1) intervalo=1;
   EventSetTimer(intervalo);
   PublicarContexto();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PublicarContexto();
}

void OnTick()
{
   // Intencionalmente vazio: este EA nunca envia ordens nem modifica posicoes.
}
