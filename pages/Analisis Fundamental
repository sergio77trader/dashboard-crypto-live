def get_fundamental_score(ticker_obj):
    # Default: Puntaje 5 (Neutro) si no hay datos
    score = 0
    details = []
    
    try:
        info = ticker_obj.info
        if not info: return 5, "Sin Datos Fundamentales"
        
        # 1. VALUATION (PEG Ratio) - Max 3 pts
        # PEG < 1 es infravalorado (Bueno), > 2 es sobrevalorado
        peg = info.get('pegRatio', None)
        if peg is not None:
            if peg < 1.0: score += 3; details.append(f"Infravalorada (PEG {peg})")
            elif peg < 2.0: score += 2; details.append(f"Precio Justo (PEG {peg})")
            else: details.append(f"Cara/Premium (PEG {peg})")
        else:
            # Fallback si no hay PEG: Usar Forward PE
            f_pe = info.get('forwardPE', 20)
            if f_pe < 15: score += 2; details.append("P/E Bajo")
            else: score += 1
            
        # 2. RENTABILIDAD (Profit Margins) - Max 3 pts
        margins = info.get('profitMargins', 0)
        if margins > 0.20: score += 3; details.append("Márgenes Excelentes (>20%)")
        elif margins > 0.10: score += 2; details.append("Márgenes Buenos")
        elif margins > 0: score += 1; details.append("Rentable")
        else: details.append("⚠️ Pierde Dinero (Márgenes Negativos)")
        
        # 3. CRECIMIENTO (Revenue Growth) - Max 2 pts
        rev_g = info.get('revenueGrowth', 0)
        if rev_g > 0.15: score += 2; details.append("Crecimiento Alto (>15%)")
        elif rev_g > 0: score += 1; details.append("En Crecimiento")
        
        # 4. CONSENSO ANALISTAS (Target Price) - Max 2 pts
        curr_price = info.get('currentPrice', 0)
        target_price = info.get('targetMeanPrice', 0)
        
        if target_price > 0 and curr_price > 0:
            upside = (target_price - curr_price) / curr_price
            if upside > 0.20: score += 2; details.append(f"Analistas ven +{upside:.0%} subida")
            elif upside > 0.05: score += 1
            else: details.append("Precio cerca del objetivo de analistas")
            
        return score, details
        
    except:
        return 5, ["Error descarga fundamental"]
