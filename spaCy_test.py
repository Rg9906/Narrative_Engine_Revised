import spacy
print('spacy_version', spacy.__version__)
nlp = spacy.load('en_core_web_sm')
doc = nlp('Alice went to the Silver Gate. She looked around.')
print('model_loaded')
print('sentences', len(list(doc.sents)))
print('ents', [(ent.text, ent.label_) for ent in doc.ents])
