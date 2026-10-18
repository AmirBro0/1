// Also read actual detector metadata from servers started before scope was added.
// An archive entry must never inherit the current server's detector settings.
export function analysisScope(record={}){
  const stored=record.analysis_scope||record.result?.analysis_scope;
  if(stored&&typeof stored==='object')return stored;
  const names=record.result?.detectors||record.detectors;
  if(Array.isArray(names)&&names.length&&names.every(name=>name==='obstruction'))return {
    mode:'camera_visibility',label:'Проверка видимости камеры',checked_rule_ids:['V13'],
    team_model:{enabled:false,available:false},full_audit_available:false,
    verdict_labels:{violation:'Есть признаки перекрытия камеры',no_violation:'Признаков перекрытия камеры не найдено'},
    limitations:['Проверяется только V13: признаки перекрытия или сильного затемнения камеры.',
      'Алгоритм использует яркость, контраст и детали кадра; LLM для этой проверки не нужна.',
      'Кассовые операции и остальные типы каталога автоматически не проверяются.'],
  };
  return {mode:'unknown',label:'Проверка видео',limitations:['Область распознавания не указана. Отсутствие отметок не означает отсутствие всех нарушений.']};
}
