# AUTOGENERATED BY NBDEV! DO NOT EDIT!

__all__ = ["index", "modules", "custom_doc_links", "git_url"]

index = {"Singleton": "00_utils.ipynb",
         "str_to_type": "00_utils.ipynb",
         "print_versions": "00_utils.ipynb",
         "set_seed": "00_utils.ipynb",
         "PreCalculatedLoss": "00_utils.ipynb",
         "PreCalculatedCrossEntropyLoss": "00_utils.ipynb",
         "PreCalculatedBCELoss": "00_utils.ipynb",
         "PreCalculatedMSELoss": "00_utils.ipynb",
         "MultiTargetLoss": "00_utils.ipynb",
         "get_hf_objects": "01_text-utils.ipynb",
         "BlurrText": "01_text-utils.ipynb",
         "Preprocessor": "11_text-data-core.ipynb",
         "ClassificationPreprocessor": "11_text-data-core.ipynb",
         "TextInput": "11_text-data-core.ipynb",
         "BatchTokenizeTransform": "11_text-data-core.ipynb",
         "BatchDecodeTransform": "11_text-data-core.ipynb",
         "blurr_sort_func": "11_text-data-core.ipynb",
         "TextBlock": "11_text-data-core.ipynb",
         "get_blurr_tfm": "11_text-data-core.ipynb",
         "first_blurr_tfm": "11_text-data-core.ipynb",
         "TextBatchCreator": "11_text-data-core.ipynb",
         "TextDataLoader": "11_text-data-core.ipynb",
         "preproc_hf_dataset": "11_text-data-core.ipynb",
         "blurr_splitter": "11_text-modeling-core.ipynb",
         "BaseModelWrapper": "11_text-modeling-core.ipynb",
         "BaseModelCallback": "11_text-modeling-core.ipynb",
         "Learner.blurr_predict": "11_text-modeling-core.ipynb",
         "Learner.blurr_generate": "11_text-modeling-core.ipynb",
         "Blearner": "11_text-modeling-core.ipynb",
         "BlearnerForSequenceClassification": "11_text-modeling-core.ipynb",
         "LMPreprocessor": "12_text-data-language-modeling.ipynb",
         "LMType": "12_text-data-language-modeling.ipynb",
         "BaseLMStrategy": "12_text-data-language-modeling.ipynb",
         "CausalLMStrategy": "12_text-data-language-modeling.ipynb",
         "BertMLMStrategy": "12_text-data-language-modeling.ipynb",
         "CausalLMTextInput": "12_text-data-language-modeling.ipynb",
         "MLMTextInput": "12_text-data-language-modeling.ipynb",
         "LMBatchTokenizeTransform": "12_text-data-language-modeling.ipynb",
         "LMMetricsCallback": "12_text-modeling-language-modeling.ipynb",
         "Learner.blurr_fill_mask": "12_text-modeling-language-modeling.ipynb",
         "BlearnerForLM": "12_text-modeling-language-modeling.ipynb",
         "TokenClassPreprocessor": "13_text-data-token-classification.ipynb",
         "BaseLabelingStrategy": "13_text-data-token-classification.ipynb",
         "OnlyFirstTokenLabelingStrategy": "13_text-data-token-classification.ipynb",
         "SameLabelLabelingStrategy": "13_text-data-token-classification.ipynb",
         "BILabelingStrategy": "13_text-data-token-classification.ipynb",
         "get_token_labels_from_input_ids": "13_text-data-token-classification.ipynb",
         "get_word_labels_from_token_labels": "13_text-data-token-classification.ipynb",
         "TokenTensorCategory": "13_text-data-token-classification.ipynb",
         "TokenCategorize": "13_text-data-token-classification.ipynb",
         "TokenCategoryBlock": "13_text-data-token-classification.ipynb",
         "TokenClassTextInput": "13_text-data-token-classification.ipynb",
         "TokenClassBatchTokenizeTransform": "13_text-data-token-classification.ipynb",
         "calculate_token_class_metrics": "13_text-modeling-token-classification.ipynb",
         "TokenClassMetricsCallback": "13_text-modeling-token-classification.ipynb",
         "TokenAggregationStrategies": "13_text-modeling-token-classification.ipynb",
         "Learner.blurr_predict_tokens": "13_text-modeling-token-classification.ipynb",
         "BlearnerForTokenClassification": "13_text-modeling-token-classification.ipynb",
         "QAPreprocessor": "14_text-data-question-answering.ipynb",
         "QATextInput": "14_text-data-question-answering.ipynb",
         "QABatchTokenizeTransform": "14_text-data-question-answering.ipynb",
         "squad_metric": "14_text-modeling-question-answering.ipynb",
         "QAModelCallback": "14_text-modeling-question-answering.ipynb",
         "QAMetricsCallback": "14_text-modeling-question-answering.ipynb",
         "compute_qa_metrics": "14_text-modeling-question-answering.ipynb",
         "PreCalculatedQALoss": "14_text-modeling-question-answering.ipynb",
         "Learner.blurr_predict_answers": "14_text-modeling-question-answering.ipynb",
         "BlearnerForQuestionAnswering": "14_text-modeling-question-answering.ipynb",
         "Seq2SeqPreprocessor": "20_text-data-seq2seq-core.ipynb",
         "Seq2SeqTextInput": "20_text-data-seq2seq-core.ipynb",
         "Seq2SeqBatchTokenizeTransform": "20_text-data-seq2seq-core.ipynb",
         "Seq2SeqBatchDecodeTransform": "20_text-data-seq2seq-core.ipynb",
         "default_text_gen_kwargs": "20_text-data-seq2seq-core.ipynb",
         "Seq2SeqTextBlock": "20_text-data-seq2seq-core.ipynb",
         "blurr_seq2seq_splitter": "20_text-modeling-seq2seq-core.ipynb",
         "Seq2SeqMetricsCallback": "20_text-modeling-seq2seq-core.ipynb",
         "SummarizationPreprocessor": "21_text-data-seq2seq-summarization.ipynb",
         "Learner.blurr_summarize": "21_text-modeling-seq2seq-summarization.ipynb",
         "BlearnerForSummarization": "21_text-modeling-seq2seq-summarization.ipynb",
         "TranslationPreprocessor": "22_text-data-seq2seq-translation.ipynb",
         "Learner.blurr_translate": "22_text-modeling-seq2seq-translation.ipynb",
         "BlearnerForTranslation": "22_text-modeling-seq2seq-translation.ipynb"}

modules = ["callbacks.py",
           "utils.py",
           "text/callbacks.py",
           "text/utils.py",
           "text/data/core.py",
           "text/modeling/core.py",
           "text/data/language_modeling.py",
           "text/modeling/language_modeling.py",
           "text/data/token_classification.py",
           "text/modeling/token_classification.py",
           "text/data/question_answering.py",
           "text/modeling/question_answering.py",
           "text/data/seq2seq/core.py",
           "text/modeling/seq2seq/core.py",
           "text/data/seq2seq/summarization.py",
           "text/modeling/seq2seq/summarization.py",
           "text/data/seq2seq/translation.py",
           "text/modeling/seq2seq/translation.py",
           "examples/text/high_level_api.py",
           "examples/text/glue.py",
           "examples/text/glue_low_level_api.py",
           "examples/text/multilabel_classification.py",
           "examples/text/causal_lm_gpt2.py"]

doc_url = "https://ohmeow.github.io/blurr/"

git_url = "https://github.com/ohmeow/blurr/tree/master/"

def custom_doc_links(name): return None
