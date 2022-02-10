# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/04_modeling-question-answering.ipynb (unless otherwise specified).

__all__ = ['HF_QstAndAnsModelCallback', 'MultiTargetLoss', 'BlearnerForQuestionAnswering']

# Cell
import os, ast, inspect
from typing import Any, Callable, Dict, List, Optional, Union, Type

from fastcore.all import *
from fastai.callback.all import *
from fastai.data.block import DataBlock, CategoryBlock, ColReader, ItemGetter, ColSplitter, RandomSplitter
from fastai.data.core import DataLoader, DataLoaders, TfmdDL
from fastai.imports import *
from fastai.learner import *
from fastai.losses import CrossEntropyLossFlat
from fastai.optimizer import Adam, OptimWrapper, params
from fastai.torch_core import *
from fastai.torch_imports import *
from fastprogress.fastprogress import progress_bar,master_bar
from seqeval import metrics as seq_metrics
from transformers import (
    AutoModelForQuestionAnswering, logging,
    PretrainedConfig, PreTrainedTokenizerBase, PreTrainedModel
)

from ..utils import BLURR
from ..data.core import HF_TextBlock, BlurrDataLoader, first_blurr_tfm
from .core import HF_BaseModelCallback, HF_PreCalculatedLoss, Blearner
from ..data.question_answering import HF_QuestionAnswerInput, HF_QABeforeBatchTransform

logging.set_verbosity_error()

# Cell
class HF_QstAndAnsModelCallback(HF_BaseModelCallback):
    """The prediction is a combination start/end logits"""
    def after_pred(self):
        super().after_pred()
        self.learn.pred = (self.pred.start_logits, self.pred.end_logits)

# Cell
class MultiTargetLoss(Module):
    """Provides the ability to apply different loss functions to multi-modal targets/predictions"""
    def __init__(
        self,
        # The loss function for each target
        loss_classes:List[Callable]=[CrossEntropyLossFlat, CrossEntropyLossFlat],
        # Any kwargs you want to pass to the loss functions above
        loss_classes_kwargs:List[dict]=[{}, {}],
        # The weights you want to apply to each loss (default: [1,1])
        weights:Union[List[float], List[int]]=[1, 1],
        # The `reduction` parameter of the lass function (default: 'mean')
        reduction:str='mean'
    ):
        loss_funcs = [ cls(reduction=reduction, **kwargs) for cls, kwargs in zip(loss_classes, loss_classes_kwargs) ]
        store_attr(self=self, names='loss_funcs, weights')
        self._reduction = reduction

    # custom loss function must have either a reduction attribute or a reduction argument (like all fastai and
    # PyTorch loss functions) so that the framework can change this as needed (e.g., when doing lear.get_preds
    # it will set = 'none'). see this forum topic for more info: https://bit.ly/3br2Syz
    @property
    def reduction(self): return self._reduction

    @reduction.setter
    def reduction(self, v):
        self._reduction = v
        for lf in self.loss_funcs: lf.reduction = v

    def forward(self, outputs, *targets):
        loss = 0.
        for i, loss_func, weights, output, target in zip(range(len(outputs)),
                                                         self.loss_funcs, self.weights,
                                                         outputs, targets):
            loss += weights * loss_func(output, target)

        return loss

    def activation(self, outs):
        return [ self.loss_funcs[i].activation(o) for i, o in enumerate(outs) ]

    def decodes(self, outs):
        return [ self.loss_funcs[i].decodes(o) for i, o in enumerate(outs) ]


# Cell
@typedispatch
def show_results(
    # This typedispatched `show_results` will be called for `HF_QuestionAnswerInput` typed inputs
    x:HF_QuestionAnswerInput,
    # The targets
    y,
    # Your raw inputs/targets
    samples,
    # The model's predictions
    outs,
    # Your `Learner`. This is required so as to get at the Hugging Face objects for decoding them into
    # something understandable
    learner,
    # Whether you want to remove special tokens during decoding/showing the outputs
    skip_special_tokens=True,
    # Your `show_results` context
    ctxs=None,
    # The maximum number of items to show
    max_n=6,
     # Any truncation your want applied to your decoded inputs
    trunc_at=None,
    # Any other keyword arguments you want applied to `show_results`
    **kwargs
):
    tfm = first_blurr_tfm(learner.dls)
    hf_tokenizer = tfm.hf_tokenizer

    res = L()
    for sample, input_ids, start, end, pred in zip(samples, x, *y, outs):
        txt = hf_tokenizer.decode(sample[0], skip_special_tokens=True)[:trunc_at]
        ans_toks = hf_tokenizer.convert_ids_to_tokens(input_ids, skip_special_tokens=False)[start:end]
        pred_ans_toks = hf_tokenizer.convert_ids_to_tokens(input_ids, skip_special_tokens=False)[int(pred[0]):int(pred[1])]

        res.append((txt,
                    (start.item(),end.item()), hf_tokenizer.convert_tokens_to_string(ans_toks),
                    (int(pred[0]),int(pred[1])), hf_tokenizer.convert_tokens_to_string(pred_ans_toks)))

    df = pd.DataFrame(res, columns=['text', 'start/end', 'answer', 'pred start/end', 'pred answer'])
    display_df(df[:max_n])
    return ctxs

# Cell
@delegates(Blearner.__init__)
class BlearnerForQuestionAnswering(Blearner):

    def __init__(
        self,
        dls:DataLoaders,
        hf_model: PreTrainedModel,
        **kwargs
    ):
        kwargs['loss_func'] = kwargs.get('loss_func', MultiTargetLoss())
        super().__init__(dls, hf_model, base_model_cb=HF_QstAndAnsModelCallback, **kwargs)

    @classmethod
    def get_model_cls(self):
        return AutoModelForQuestionAnswering

    @classmethod
    def _get_x(
        cls,
        x,
        qst,
        ctx,
        padding_side='right'
    ):
         return (x[qst], x[ctx]) if (padding_side == 'right') else (x[ctx], x[qst])

    @classmethod
    def _create_learner(
        cls,
        # Your raw dataset
        data,
        # The name or path of the pretrained model you want to fine-tune
        pretrained_model_name_or_path:Optional[Union[str, os.PathLike]],
        # A function to perform any preprocessing required for your Dataset
        preprocess_func:Callable=None,
        # The maximum sequence length to constrain our data
        max_seq_len:int=None,
        # The attribute in your dataset that contains the context (where the answer is included) (default: 'context')
        context_attr:str='context',
        # The attribute in your dataset that contains the question being asked (default: 'question')
        question_attr:str='question',
        # The attribute in your dataset that contains the actual answer (default: 'answer_text')
        answer_text_attr:str='answer_text',
        # The attribute in your dataset that contains the tokenized answer start (default: 'tok_answer_start')
        tok_ans_start_attr:str='tok_answer_start',
        # The attribute in your dataset that contains the tokenized answer end(default: 'tok_answer_end')
        tok_ans_end_attr:str='tok_answer_end',
        # A function that will split your Dataset into a training and validation set
        # See [here](https://docs.fast.ai/data.transforms.html#Split) for a list of fast.ai splitters
        dblock_splitter:Callable=RandomSplitter(),
        # Any kwargs to pass to your `DataLoaders`
        dl_kwargs={},
        # Any kwargs to pass to your task specific `Blearner`
        learner_kwargs={}
    ):
        hf_arch, hf_config, hf_tokenizer, hf_model = BLURR.get_hf_objects(pretrained_model_name_or_path,
                                                                          model_cls=cls.get_model_cls())

        # potentially used by our preprocess_func, it is the basis for our CategoryBlock vocab
        if (max_seq_len is None):
            max_seq_len = hf_config.get('max_position_embeddings', 128)

        # client can pass in a function that takes the raw data, hf objects, and max_seq_len ... and
        # returns a DataFrame with the expected format
        if (preprocess_func):
            data = preprocess_func(data, hf_arch, hf_config, hf_tokenizer, hf_model, max_seq_len,
                                   context_attr, question_attr, answer_text_attr,
                                   tok_ans_start_attr, tok_ans_end_attr)

        # bits required by our "before_batch_tfm" and DataBlock
        vocab = list(range(max_seq_len))
        padding_side = hf_tokenizer.padding_side
        trunc_strat = 'only_second' if (padding_side == 'right') else 'only_first'

        before_batch_tfm = HF_QABeforeBatchTransform(hf_arch, hf_config, hf_tokenizer, hf_model,
                                                     max_length=max_seq_len,
                                                     truncation=trunc_strat,
                                                     tok_kwargs={ 'return_special_tokens_mask': True })

        # define getters
        if (isinstance(data, pd.DataFrame)):
            get_x = partial(cls._get_x, qst=question_attr, ctx=context_attr, padding_side=padding_side)
            get_y = [ColReader(tok_ans_start_attr), ColReader(tok_ans_end_attr)]
        else:
            get_x = partial(cls._get_x, qst=question_attr, ctx=context_attr, padding_side=padding_side)
            get_y = [ItemGetter(tok_ans_start_attr), ItemGetter(tok_ans_end_attr)]

        # define DataBlock and DataLoaders
        blocks = (
            HF_TextBlock(before_batch_tfm=before_batch_tfm, input_return_type=HF_QuestionAnswerInput),
            CategoryBlock(vocab=vocab),
            CategoryBlock(vocab=vocab)
        )

        dblock = DataBlock(blocks=blocks,
                           get_x=get_x,
                           get_y=get_y,
                           splitter=dblock_splitter,
                           n_inp=1)

        dls = dblock.dataloaders(data, **dl_kwargs.copy())

        # return BLearner instance
        return cls(dls, hf_model, **learner_kwargs.copy())

    @classmethod
    def from_dataframe(
        cls,
        # Your pandas DataFrame
        df:pd.DataFrame,
        # The name or path of the pretrained model you want to fine-tune
        pretrained_model_name_or_path:Optional[Union[str, os.PathLike]],
        # A function to perform any preprocessing required for your Dataset
        preprocess_func:Callable=None,
        # The maximum sequence length to constrain our data
        max_seq_len:int=None,
        # The attribute in your dataset that contains the context (where the answer is included) (default: 'context')
        context_attr:str='context',
        # The attribute in your dataset that contains the question being asked (default: 'question')
        question_attr:str='question',
        # The attribute in your dataset that contains the actual answer (default: 'answer_text')
        answer_text_attr:str='answer_text',
        # The attribute in your dataset that contains the tokenized answer start (default: 'tok_answer_start')
        tok_ans_start_attr:str='tok_answer_start',
        # The attribute in your dataset that contains the tokenized answer end(default: 'tok_answer_end')
        tok_ans_end_attr:str='tok_answer_end',
        # A function that will split your Dataset into a training and validation set
        # See [here](https://docs.fast.ai/data.transforms.html#Split) for a list of fast.ai splitters
        dblock_splitter:Callable=ColSplitter(),
        # Any kwargs to pass to your `DataLoaders`
        dl_kwargs={},
        # Any kwargs to pass to your task specific `Blearner`
        learner_kwargs={}
    ):
        return cls._create_learner(df, pretrained_model_name_or_path, preprocess_func, max_seq_len,
                                   context_attr, question_attr, answer_text_attr,
                                   tok_ans_start_attr, tok_ans_end_attr, dblock_splitter,
                                   dl_kwargs, learner_kwargs)

    @classmethod
    def from_csv(
        cls,
        # The path to your csv file
        csv_file:Union[Path, str],
        # The name or path of the pretrained model you want to fine-tune
        pretrained_model_name_or_path:Optional[Union[str, os.PathLike]],
        # A function to perform any preprocessing required for your Dataset
        preprocess_func:Callable=None,
        # The maximum sequence length to constrain our data
        max_seq_len:int=None,
        # The attribute in your dataset that contains the context (where the answer is included) (default: 'context')
        context_attr:str='context',
        # The attribute in your dataset that contains the question being asked (default: 'question')
        question_attr:str='question',
        # The attribute in your dataset that contains the actual answer (default: 'answer_text')
        answer_text_attr:str='answer_text',
        # The attribute in your dataset that contains the tokenized answer start (default: 'tok_answer_start')
        tok_ans_start_attr:str='tok_answer_start',
        # The attribute in your dataset that contains the tokenized answer end(default: 'tok_answer_end')
        tok_ans_end_attr:str='tok_answer_end',
        # A function that will split your Dataset into a training and validation set
        # See [here](https://docs.fast.ai/data.transforms.html#Split) for a list of fast.ai splitters
        dblock_splitter:Callable=ColSplitter(),
        # Any kwargs to pass to your `DataLoaders`
        dl_kwargs={},
        # Any kwargs to pass to your task specific `Blearner`
        learner_kwargs={}
    ):
        df = pd.read_csv(csv_file)

        return cls.from_dataframe(df, pretrained_model_name_or_path, preprocess_func, max_seq_len,
                                  context_attr, question_attr, answer_text_attr,
                                  tok_ans_start_attr, tok_ans_end_attr, dblock_splitter,
                                  dl_kwargs, learner_kwargs)

    @classmethod
    def from_dictionaries(
        cls,
        # A list of dictionaries
        ds:List[Dict],
        # The name or path of the pretrained model you want to fine-tune
        pretrained_model_name_or_path:Optional[Union[str, os.PathLike]],
        # A function to perform any preprocessing required for your Dataset
        preprocess_func:Callable=None,
        # The maximum sequence length to constrain our data
        max_seq_len:int=None,
        # The attribute in your dataset that contains the context (where the answer is included) (default: 'context')
        context_attr:str='context',
        # The attribute in your dataset that contains the question being asked (default: 'question')
        question_attr:str='question',
        # The attribute in your dataset that contains the actual answer (default: 'answer_text')
        answer_text_attr:str='answer_text',
        # The attribute in your dataset that contains the tokenized answer start (default: 'tok_answer_start')
        tok_ans_start_attr:str='tok_answer_start',
        # The attribute in your dataset that contains the tokenized answer end(default: 'tok_answer_end')
        tok_ans_end_attr:str='tok_answer_end',
        # A function that will split your Dataset into a training and validation set
        # See [here](https://docs.fast.ai/data.transforms.html#Split) for a list of fast.ai splitters
        dblock_splitter:Callable=RandomSplitter(),
        # Any kwargs to pass to your `DataLoaders`
        dl_kwargs={},
        # Any kwargs to pass to your task specific `Blearner`
        learner_kwargs={}
    ):
        return cls._create_learner(ds, pretrained_model_name_or_path, preprocess_func, max_seq_len,
                                   context_attr, question_attr, answer_text_attr,
                                   tok_ans_start_attr, tok_ans_end_attr, dblock_splitter,
                                   dl_kwargs, learner_kwargs)