def format_final_summary(summary: str, style: str = "narrative") -> str:
    """Форматирует финальное резюме в соответствии с выбранным стилем"""
    if style == "bullets":
        # Преобразуем в маркированный список, если это еще не сделано
        lines = summary.split('\n')
        bullet_points = []
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('- '):
                bullet_points.append(f"- {line}")
            elif line:
                bullet_points.append(line)
        
        return "\n".join(bullet_points)
    
    return summary  # Для narrative стиля оставляем как есть