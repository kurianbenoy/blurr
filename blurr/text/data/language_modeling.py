# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/12_text-data-language-modeling.ipynb (unless otherwise specified).

__all__ = ['LMPreprocessor', 'LMType', 'BaseLMStrategy', 'CausalLMStrategy', 'BertMLMStrategy', 'CausalLMTextInput',
           'MLMTextInput', 'LMBatchTokenizeTransform']

# Cell
import os, random
from abc import ABC, abstractmethod
from enum import Enum

from datasets import Dataset
from fastcore.all import *
from fastai.imports import *
from fastai.losses import CrossEntropyLossFlat
from fastai.torch_core import *
from fastai.torch_imports import *
from transformers import (
    AutoModelForCausalLM,
    AutoModelForMaskedLM,
    logging,
    PretrainedConfig,
    PreTrainedTokenizerBase,
    PreTrainedModel,
    BatchEncoding,
)

from .core import TextInput, BatchTokenizeTransform, Preprocessor, first_blurr_tfm
from ..utils import get_hf_objects

logging.set_verbosity_error()


# Cell
class LMPreprocessor(Preprocessor):
    def __init__(
        self,
        # A Hugging Face tokenizer
        hf_tokenizer: PreTrainedTokenizerBase,
        # The number of examples to process at a time
        batch_size: int = 1000,
        # How big each chunk of text should be (default: hf_tokenizer.model_max_length)
        chunk_size: Optional[int] = None,
        # How to indicate the beginning on a new text example (default is hf_tokenizer.eos_token|sep_token
        sep_token: Optional[str] = None,
        # The attribute holding the text
        text_attr: str = "text",
        # The attribute that should be created if your are processing individual training and validation
        # datasets into a single dataset, and will indicate to which each example is associated
        is_valid_attr: Optional[str] = "is_valid",
        # Tokenization kwargs that will be applied with calling the tokenizer
        tok_kwargs: dict = {},
    ):
        tok_kwargs = {**tok_kwargs, "truncation": False, "return_offsets_mapping": True}
        super().__init__(hf_tokenizer, batch_size, text_attr, None, is_valid_attr, tok_kwargs)

        self.chunk_size = chunk_size or hf_tokenizer.model_max_length
        self.sep_token = sep_token or hf_tokenizer.eos_token or hf_tokenizer.sep_token

    def process_df(self, training_df: pd.DataFrame, validation_df: Optional[pd.DataFrame] = None):
        # process df in mini-batches
        final_train_df = pd.DataFrame()
        for g, batch_df in training_df.groupby(np.arange(len(training_df)) // self.batch_size):
            final_train_df = final_train_df.append(self._process_df_batch(batch_df))
            final_train_df.reset_index(drop=True, inplace=True)

        final_val_df = pd.DataFrame() if validation_df is not None else None
        if final_val_df is not None:
            for g, batch_df in validation_df.groupby(np.arange(len(validation_df)) // self.batch_size):
                final_val_df = final_val_df.append(self._process_df_batch(batch_df))
                final_val_df.reset_index(drop=True, inplace=True)

        final_df = super().process_df(final_train_df, final_val_df)
        return final_df

    def process_hf_dataset(self, training_ds: Dataset, validation_ds: Optional[Dataset] = None):
        ds = super().process_hf_dataset(training_ds, validation_ds)
        return Dataset.from_pandas(self.process_df(pd.DataFrame(ds)))

    # ----- utility methods -----
    def _process_df_batch(self, batch_df):
        batch_df.reset_index(drop=True, inplace=True)

        # concatenate our texts
        concat_txts = {self.text_attr: f" {self.sep_token} ".join(batch_df[self.text_attr].values.tolist())}
        inputs = self._tokenize_function(concat_txts)

        # compute the length of our concatenated texts
        n_total_toks = len(inputs["input_ids"])

        # need to modify chunk_size to included the # of special tokens added
        max_chunk_size = self.chunk_size - self.hf_tokenizer.num_special_tokens_to_add() - 1

        # drop the last chunk of text if it is smaller than chunk size (see the HF course, section 7 on training MLMs)
        total_length = (n_total_toks // max_chunk_size) * max_chunk_size

        # break our concatenated into chunks of text of size max_chunk_size
        examples = []
        for i in range(0, total_length, max_chunk_size):
            chunked_offsets = inputs["offset_mapping"][i : i + max_chunk_size]
            chunked_text = concat_txts[self.text_attr][min(chunked_offsets)[0] : max(chunked_offsets)[1]]
            examples.append(chunked_text)

        return pd.DataFrame(examples, columns=[f"proc_{self.text_attr}"])


# Cell
class LMType(Enum):
    """Use this enum to indicate what kind of language model you are training"""

    CAUSAL = 1
    MASKED = 2


# Cell
class BaseLMStrategy(ABC):
    """ABC for various language modeling strategies (e.g., causal, BertMLM, WholeWordMLM, etc...)"""

    def __init__(self, hf_tokenizer, ignore_token_id=CrossEntropyLossFlat().ignore_index):
        store_attr(["hf_tokenizer", "ignore_token_id"])

    @abstractmethod
    def build_inputs_targets(self, samples, include_labels: bool = True, inputs: Optional[BatchEncoding] = None):
        pass

    # utility methods
    def _get_random_token_id(self, n):
        return random.sample(list(self.hf_tokenizer.get_vocab().values()), n)

    @classmethod
    @abstractmethod
    def get_lm_type(cls):
        pass


# Cell
class CausalLMStrategy(BaseLMStrategy):
    """For next token prediction language modeling tasks, we want to use the `CausalLMStrategy` which makes the
    necessary changes in your inputs/targets for causal LMs
    """

    def build_inputs_targets(self, samples, include_labels: bool = True, inputs: Optional[BatchEncoding] = None):
        updated_samples = []
        for s in samples:
            if include_labels:
                s[0]["labels"] = s[0]["input_ids"].clone()
                s[0]["labels"][s[0]["labels"] == self.hf_tokenizer.pad_token_id] = self.ignore_token_id

            targ_ids = torch.cat([s[0]["input_ids"][1:], tensor([self.hf_tokenizer.eos_token_id])])

            updated_samples.append((s[0], targ_ids))

        return updated_samples

    @classmethod
    def get_lm_type(cls: LMType):
        return LMType.CAUSAL


# Cell
class BertMLMStrategy(BaseLMStrategy):
    """A masked language modeling strategy using the default BERT masking definition."""

    def __init__(self, hf_tokenizer, ignore_token_id=CrossEntropyLossFlat().ignore_index):
        super().__init__(hf_tokenizer, ignore_token_id)

        vocab = hf_tokenizer.get_vocab()
        self.dnm_tok_ids = [
            vocab[tok] for tok in list(hf_tokenizer.special_tokens_map.values()) if vocab[tok] != hf_tokenizer.mask_token_id
        ]

    def build_inputs_targets(self, samples, include_labels: bool = True, inputs: Optional[BatchEncoding] = None):
        updated_samples = []
        for s in samples:
            # mask the input_ids
            masked_input_ids = s[0]["input_ids"].clone()

            # we want to mask 15% of the non-special tokens(e.g., special tokens inclue [CLS], [SEP], etc...)
            idxs = torch.randperm(len(masked_input_ids))
            total_masked_idxs = int(len(idxs) * 0.15)

            # of the 15% for masking, replace 80% with [MASK] token, 10% with random token, and 10% with correct token
            n_mask_idxs = int(total_masked_idxs * 0.8)
            n_rnd_idxs = int(total_masked_idxs * 0.1)

            # we only want non-special tokens
            mask_idxs = [idx for idx in idxs if masked_input_ids[idx] not in self.dnm_tok_ids][:total_masked_idxs]

            # replace 80% with [MASK]
            if n_mask_idxs > 0 and len(mask_idxs) >= n_mask_idxs:
                masked_input_ids[[mask_idxs[:n_mask_idxs]]] = self.hf_tokenizer.mask_token_id

            # replace 10% with a random token
            if n_rnd_idxs > 0 and len(mask_idxs) >= (n_mask_idxs + n_rnd_idxs):
                rnd_tok_ids = self._get_random_token_id(n_rnd_idxs)
                masked_input_ids[[mask_idxs[n_mask_idxs : (n_mask_idxs + n_rnd_idxs)]]] = tensor(rnd_tok_ids)

            # ignore padding when calculating the loss
            lbls = s[0]["input_ids"].clone()
            lbls[[[idx for idx in idxs if idx not in mask_idxs]]] = self.ignore_token_id

            # update the inputs to use our masked input_ids and labels; set targ_ids = labels (will use when
            # we calculate the loss ourselves)
            s[0]["input_ids"] = masked_input_ids
            targ_ids = lbls

            if include_labels:
                s[0]["labels"] = targ_ids.clone()

            updated_samples.append((s[0], targ_ids))

        return updated_samples

    @classmethod
    def get_lm_type(cls: LMType):
        return LMType.MASKED


# Cell
class CausalLMTextInput(TextInput):
    pass


# export
class MLMTextInput(TextInput):
    pass


# Cell
class LMBatchTokenizeTransform(BatchTokenizeTransform):
    def __init__(
        self,
        # The abbreviation/name of your Hugging Face transformer architecture (e.b., bert, bart, etc..)
        hf_arch: str,
        # A specific configuration instance you want to use
        hf_config: PretrainedConfig,
        # A Hugging Face tokenizer
        hf_tokenizer: PreTrainedTokenizerBase,
        # A Hugging Face model
        hf_model: PreTrainedModel,
        # To control whether the "labels" are included in your inputs. If they are, the loss will be calculated in
        # the model's forward function and you can simply use `PreCalculatedLoss` as your `Learner`'s loss function to use it
        include_labels: bool = True,
        # The token ID that should be ignored when calculating the loss
        ignore_token_id: int = CrossEntropyLossFlat().ignore_index,
        # The language modeling strategy (or objective)
        lm_strategy_cls: BaseLMStrategy = CausalLMStrategy,
        # To control the length of the padding/truncation. It can be an integer or None,
        # in which case it will default to the maximum length the model can accept. If the model has no
        # specific maximum input length, truncation/padding to max_length is deactivated.
        # See [Everything you always wanted to know about padding and truncation](https://huggingface.co/transformers/preprocessing.html#everything-you-always-wanted-to-know-about-padding-and-truncation)
        max_length: int = None,
        # To control the `padding` applied to your `hf_tokenizer` during tokenization. If None, will default to
        # `False` or `'do_not_pad'.
        # See [Everything you always wanted to know about padding and truncation](https://huggingface.co/transformers/preprocessing.html#everything-you-always-wanted-to-know-about-padding-and-truncation)
        padding: Union[bool, str] = True,
        # To control `truncation` applied to your `hf_tokenizer` during tokenization. If None, will default to
        # `False` or `do_not_truncate`.
        # See [Everything you always wanted to know about padding and truncation](https://huggingface.co/transformers/preprocessing.html#everything-you-always-wanted-to-know-about-padding-and-truncation)
        truncation: Union[bool, str] = True,
        # The `is_split_into_words` argument applied to your `hf_tokenizer` during tokenization. Set this to `True`
        # if your inputs are pre-tokenized (not numericalized)
        is_split_into_words: bool = False,
        # Any other keyword arguments you want included when using your `hf_tokenizer` to tokenize your inputs
        tok_kwargs={},
        # Any keyword arguments you want included when generated text
        # See [How to generate text](https://huggingface.co/blog/how-to-generate)
        text_gen_kwargs={},
        # Keyword arguments to apply to `BatchTokenizeTransform`
        **kwargs
    ):
        super().__init__(
            hf_arch,
            hf_config,
            hf_tokenizer,
            hf_model,
            include_labels=include_labels,
            ignore_token_id=ignore_token_id,
            max_length=max_length,
            padding=padding,
            truncation=truncation,
            is_split_into_words=is_split_into_words,
            tok_kwargs=tok_kwargs.copy(),
            **kwargs
        )

        self.lm_strategy = lm_strategy_cls(hf_tokenizer=hf_tokenizer, ignore_token_id=ignore_token_id)
        self.text_gen_kwargs, self.ignore_token_id = text_gen_kwargs, ignore_token_id

    def encodes(self, samples, return_batch_encoding=False):
        # because no target is specific in CLM, fastai will duplicate the inputs (which is just the raw text)
        samples, inputs = super().encodes(samples, return_batch_encoding=True)
        if len(samples[0]) == 1:
            return samples

        updated_samples = self.lm_strategy.build_inputs_targets(samples, self.include_labels, inputs)

        if return_batch_encoding:
            return updated_samples, inputs

        return updated_samples


# Cell
@typedispatch
def show_batch(
    # This typedispatched `show_batch` will be called for `CausalLMTextInput` typed inputs
    x: CausalLMTextInput,
    # Your targets
    y,
    # Your raw inputs/targets
    samples,
    # Your `DataLoaders`. This is required so as to get at the Hugging Face objects for
    # decoding them into something understandable
    dataloaders,
    # Your `show_batch` context
    ctxs=None,
    # The maximum number of items to show
    max_n=6,
    # Any truncation your want applied to your decoded inputs
    trunc_at=None,
    # Any other keyword arguments you want applied to `show_batch`
    **kwargs
):
    # grab our tokenizer and ignore token to decode
    tfm = first_blurr_tfm(dataloaders)
    hf_tokenizer = tfm.hf_tokenizer
    ignore_token_id = tfm.ignore_token_id

    res = L(
        [
            (
                hf_tokenizer.decode(s[0], skip_special_tokens=False)[:trunc_at],
                hf_tokenizer.decode(s[1][s[1] != ignore_token_id], skip_special_tokens=True)[:trunc_at],
            )
            for s in samples
        ]
    )

    display_df(pd.DataFrame(res, columns=["text", "target"])[:max_n])
    return ctxs


# Cell
@typedispatch
def show_batch(
    # This typedispatched `show_batch` will be called for `MLMTextInput` typed inputs
    x: MLMTextInput,
    # Your targets
    y,
    # Your raw inputs/targets
    samples,
    # Your `DataLoaders`. This is required so as to get at the Hugging Face objects for
    # decoding them into something understandable
    dataloaders,
    # Your `show_batch` context
    ctxs=None,
    # The maximum number of items to show
    max_n=6,
    # Any truncation your want applied to your decoded inputs
    trunc_at=None,
    # Any other keyword arguments you want applied to `show_batch`
    **kwargs,
):
    # grab our tokenizer and ignore token to decode
    tfm = first_blurr_tfm(dataloaders)
    hf_tokenizer = tfm.hf_tokenizer
    ignore_token_id = tfm.ignore_token_id

    # grab our mask token id and do-not-mask token ids
    mask_token_id = hf_tokenizer.mask_token_id

    vocab = hf_tokenizer.get_vocab()
    dnm_tok_ids = [vocab[tok] for tok in list(hf_tokenizer.special_tokens_map.values()) if vocab[tok] != mask_token_id]

    res = L()
    for s in samples:
        # exclue dnm tokens from input
        inps = [
            hf_tokenizer.decode(tok_id) if (tok_id == mask_token_id or s[1][idx] == ignore_token_id) else f"[{hf_tokenizer.decode(tok_id)}]"
            for idx, tok_id in enumerate(s[0])
            if (tok_id not in dnm_tok_ids)
        ]

        # replaced masked tokens with "[{actual_token}]"
        trgs = [
            hf_tokenizer.decode(s[0][idx]) if (tok_id == ignore_token_id) else f"[{hf_tokenizer.decode(tok_id)}]"
            for idx, tok_id in enumerate(s[1])
            if (s[0][idx] not in dnm_tok_ids)
        ]

        res.append((" ".join(inps[:trunc_at]).strip(), " ".join(trgs[:trunc_at]).strip()))

    display_df(pd.DataFrame(res, columns=["text", "target"])[:max_n])
    return ctxs
