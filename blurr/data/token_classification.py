# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/03_data-token-classification.ipynb (unless otherwise specified).

__all__ = ['BaseLabelingStrategy', 'OnlyFirstTokenLabelingStrategy', 'SameLabelLabelingStrategy', 'BILabelingStrategy',
           'get_token_labels_from_input_ids', 'get_word_labels_from_token_labels', 'TokenClassificationPreprocessor',
           'HF_TokenTensorCategory', 'HF_TokenCategorize', 'HF_TokenCategoryBlock', 'HF_TokenClassInput',
           'HF_TokenClassBeforeBatchTransform']

# Cell
import ast, os
from typing import Callable, List, Tuple

from datasets import Dataset
from fastcore.all import *
from fastai.data.block import TransformBlock, Category, CategoryMap
from fastai.imports import *
from fastai.losses import CrossEntropyLossFlat
from fastai.torch_core import *
from fastai.torch_imports import *
from transformers import AutoModelForTokenClassification, logging, PretrainedConfig, PreTrainedTokenizerBase, PreTrainedModel

from ..utils import BLURR
from .core import Preprocessor, HF_BaseInput, HF_BeforeBatchTransform, first_blurr_tfm

logging.set_verbosity_error()


# Cell
class BaseLabelingStrategy:
    def __init__(self, hf_tokenizer: PreTrainedTokenizerBase, ignore_token_id: int = CrossEntropyLossFlat().ignore_index) -> None:
        self.hf_tokenizer = hf_tokenizer
        self.ignore_token_id = ignore_token_id

    def align_labels_with_tokens(self, word_ids, word_labels, label_names):
        raise NotImplementedError()


# Cell
class OnlyFirstTokenLabelingStrategy(BaseLabelingStrategy):
    """
    Only the first token of word is associated with the label (all other subtokens with the `ignore_index_id`). Works where labels
    are Ids or strings (in the later case we'll use the `label_names` to look up it's Id)
    """

    def align_labels_with_tokens(self, word_ids, word_labels, label_names):
        new_labels = []
        current_word = None
        for word_id in word_ids:
            if word_id != current_word:
                # start of a new word
                current_word = word_id
                label = self.ignore_token_id if word_id is None else word_labels[word_id]
                new_labels.append(label if isinstance(label, int) else label_names.index(label))
            else:
                # special token or another subtoken of current word
                new_labels.append(self.ignore_token_id)

        return new_labels


class SameLabelLabelingStrategy(BaseLabelingStrategy):
    """
    Every token associated with a given word is associated with the word's label. Works where labels
    are Ids or strings (in the later case we'll use the `label_names` to look up it's Id)
    """

    def align_labels_with_tokens(self, word_ids, word_labels, label_names):
        new_labels = []
        for word_id in word_ids:
            if word_id == None:
                new_labels.append(self.ignore_token_id)
            else:
                label = word_labels[word_id]
                new_labels.append(label if isinstance(label, int) else label_names.index(label))

        return new_labels


class BILabelingStrategy(BaseLabelingStrategy):
    """
    If using B/I labels, the first token assoicated to a given word gets the "B" label while all other tokens related
    to that same word get "I" labels.  If "I" labels don't exist, this strategy behaves like the `OnlyFirstTokenLabelingStrategy`.
    Works where labels are Ids or strings (in the later case we'll use the `label_names` to look up it's Id)
    """

    def align_labels_with_tokens(self, word_ids, word_labels, label_names):
        new_labels = []
        current_word = None
        for word_id in word_ids:
            if word_id != current_word:
                # start of a new word
                current_word = word_id
                label = self.ignore_token_id if word_id is None else word_labels[word_id]
                new_labels.append(label if isinstance(label, int) else label_names.index(label))
            elif word_id is None:
                # special token
                new_labels.append(self.ignore_token_id)
            else:
                # we're in the same word
                label = word_labels[word_id]
                label_name = label_names[label] if isinstance(label, int) else label

                # append the I-{ENTITY} if it exists in `labels`, else default to the `same_label` strategy
                iLabel = f"I-{label_name[2:]}"
                new_labels.append(label_names.index(iLabel) if iLabel in label_names else self.ignore_token_id)

        return new_labels


# Cell
def get_token_labels_from_input_ids(
    # A Hugging Face tokenizer
    hf_tokenizer: PreTrainedTokenizerBase,
    # List of input_ids for the tokens in a single piece of processed text
    input_ids: List[int],
    # List of label indexs for each token
    token_label_ids: List[int],
    # List of label names from witch the `label` indicies can be used to find the name of the label
    vocab: List[str],
    # The token ID that should be ignored when calculating the loss
    ignore_token_id: int = CrossEntropyLossFlat().ignore_index,
    # The token used to identifiy ignored tokens (default: [xIGNx])
    ignore_token: str = "[xIGNx]",
) -> List[Tuple[str, str]]:
    """
    Given a list of input IDs, the label ID associated to each, and the labels vocab, this method will return a list of tuples whereby
    each tuple defines the "token" and its label name. For example:
    [('ĠWay', B-PER), ('de', B-PER), ('ĠGill', I-PER), ('iam', I-PER), ('Ġloves'), ('ĠHug', B-ORG), ('ging', B-ORG), ('ĠFace', I-ORG)]
    """
    # convert ids to tokens
    toks = hf_tokenizer.convert_ids_to_tokens(input_ids)
    # align "tokens" with labels
    tok_labels = [
        (tok, ignore_token if label_id == ignore_token_id else vocab[label_id])
        for tok_id, tok, label_id in zip(input_ids, toks, token_label_ids)
        if tok_id not in hf_tokenizer.all_special_ids
    ]
    return tok_labels


# Cell
def get_word_labels_from_token_labels(
    hf_arch: str,
    # A Hugging Face tokenizer
    hf_tokenizer: PreTrainedTokenizerBase,
    # A list of tuples, where each represents a token and its label (e.g., [('ĠHug', B-ORG), ('ging', B-ORG), ('ĠFace', I-ORG), ...])
    tok_labels,
) -> List[Tuple[str, str]]:
    """
    Given a list of tuples where each tuple defines a token and its label, return a list of tuples whereby each tuple defines the
    "word" and its label. Method assumes that model inputs are a list of words, and in conjunction with the `align_labels_with_tokens` method,
    allows the user to reconstruct the orginal raw inputs and labels.
    """
    # recreate raw words list (we assume for token classification that the input is a list of words)
    words = hf_tokenizer.convert_tokens_to_string([tok_label[0] for tok_label in tok_labels]).split()

    if hf_arch == "canine":
        word_list = [f"{word} " for word in words]
    else:
        word_list = [word for word in words]

    # align "words" with labels
    word_labels, idx = [], 0
    for word in word_list:
        word_labels.append((word, tok_labels[idx][1]))
        idx += len(hf_tokenizer.tokenize(word))

    return word_labels


# Cell
class TokenClassificationPreprocessor(Preprocessor):
    def __init__(
        self,
        # A Hugging Face tokenizer
        hf_tokenizer: PreTrainedTokenizerBase,
        # Set to `True` if the preprocessor should chunk examples that exceed `max_length`
        chunk_examples: bool = False,
        # Like "stride" except for words (not tokens)
        word_stride: int = 2,
        # The token ID that should be ignored when calculating the loss
        ignore_token_id: int = CrossEntropyLossFlat().ignore_index,
        # The label names (if not specified, will build from DataFrame)
        label_names: Optional[List[str]] = None,
        # The number of examples to process at a time
        batch_size: int = 1000,
        # The unique identifier in the dataset
        id_attr: Optional[str] = None,
        # The attribute holding the list of words
        word_list_attr: str = "tokens",
        # The attribute holding the list of labels (one for each word in `word_list_attr`)
        label_list_attr: str = "labels",
        # The attribute that should be created if your are processing individual training and validation
        # datasets into a single dataset, and will indicate to which each example is associated
        is_valid_attr: Optional[str] = "is_valid",
        # The labeling strategy you want to apply when associating labels with word tokens
        labeling_strategy_cls: BaseLabelingStrategy = OnlyFirstTokenLabelingStrategy,
        # If using a slow tokenizer, users will need to prove a `slow_word_ids_func` that accepts a
        # tokenizzer, example index, and a batch encoding as arguments and in turn returnes the
        # equavlient of fast tokenizer's `word_ids`
        slow_word_ids_func: Optional[Callable] = None,
        # Tokenization kwargs that will be applied with calling the tokenizer
        tok_kwargs: dict = {},
    ):
        # tokenizer requires this kwargs when tokenizing text
        tok_kwargs = {**tok_kwargs, **{"is_split_into_words": True}}

        super().__init__(hf_tokenizer, batch_size, text_attrs=word_list_attr, tok_kwargs=tok_kwargs)

        self.id_attr = id_attr
        self.label_list_attr = label_list_attr
        self.is_valid_attr = is_valid_attr
        self.label_names = label_names
        self.chunk_examples, self.word_stride = chunk_examples, word_stride

        self.slow_word_ids_func = slow_word_ids_func

        # setup our labeling strategy class
        self.labeling_strategy = labeling_strategy_cls(hf_tokenizer=hf_tokenizer, ignore_token_id=ignore_token_id)

    def process_df(self, training_df: pd.DataFrame, validation_df: Optional[pd.DataFrame] = None):
        df = super().process_df(training_df, validation_df)

        # convert even single "labels" to a list to make things easier
        if self.label_names is None:
            self.label_names = sorted(list(set([lbls for sublist in df[self.label_list_attr].tolist() for lbls in sublist])))

        # pop the `max_length` from tokenizer kwargs if we're chunking
        if self.chunk_examples:
            max_length = self.tok_kwargs.pop("max_length", self.hf_tokenizer.model_max_length)

        # tokenize in batches
        final_df = pd.DataFrame()

        if not self.chunk_examples:
            for g, batch_df in df.groupby(np.arange(len(df)) // self.batch_size):
                batch_df.reset_index(drop=True, inplace=True)
                # token classification works with lists of words, so if not listy we resort to splitting by spaces
                batch_df[self.text_attrs] = batch_df[self.text_attrs].apply(lambda v: v if is_listy(v) else v.split())

                # get the inputs inputs (e.g., input_ids, attention_mask, etc...)
                inputs = self._tokenize_function(batch_df.to_dict(orient="list"))

                # align labels with tokens
                aligned_labels = []
                for idx, word_labels in enumerate(batch_df[self.label_list_attr].values):
                    word_ids = inputs.word_ids(idx) if self.hf_tokenizer.is_fast else self.slow_word_ids_func(self.hf_tokenizer, idx, inputs)
                    aligned_labels.append(
                        self.labeling_strategy.align_labels_with_tokens(word_ids, word_labels, self.label_names)
                    )

                batch_df["aligned_labels"] = aligned_labels
                inputs_df = pd.DataFrame(dict(inputs))
                final_df = pd.concat([final_df, pd.concat([batch_df, inputs_df], axis=1)])
        else:
            # if chunking is desired, create "chunked" inputs/labels from the existing
            # input/label ensuring that words are *not* broken up between chunks
            proc_data = []
            for row_idx, row in df.iterrows():
                # fetch word list and words' label list (there should be 1 label per word)
                words, word_labels = row[self.text_attrs], row[self.label_list_attr]

                # token classification works with lists of words, so if not listy we resort to splitting by spaces
                if not is_listy(words):
                    words = words.split()

                inputs = hf_tokenizer(words, truncation=True, **self.tok_kwargs)

                # grab the inputs "word_ids"
                word_ids = inputs.word_ids() if self.hf_tokenizer.is_fast else self.slow_word_ids_func(0, inputs)

                # align labels with tokens
                aligned_labels = self.labeling_strategy.align_labels_with_tokens(word_ids, word_labels, self.label_names)

                if len(word_ids) > max_length:
                    # if the inputs are > max_length, create "chunked" inputs/labels from the existing
                    # input/label ensuring that words are *not* broken up between chunks
                    non_special_word_ids = [id for id in word_ids if id is not None]
                    max_chunk_length = max_length - self.hf_tokenizer.num_special_tokens_to_add()

                    start_idx = 0
                    current_word_id = 0
                    current_chunk_length = 0
                    chunks = []
                    while True:
                        last_idx = len(non_special_word_ids) - 1 - non_special_word_ids[::-1].index(current_word_id)
                        current_chunk_length = len(non_special_word_ids[start_idx : last_idx + 1])

                        if current_chunk_length >= max_chunk_length:
                            # we need to add a chunk
                            if current_chunk_length > max_chunk_length:
                                # only when the current chunk in > the max chunk length do we want to modify the `last_indx` (if
                                # equal then we want to use the current value)
                                last_idx = len(non_special_word_ids) - 1 - non_special_word_ids[::-1].index(max(0, current_word_id - 1))
                            chunks.append(non_special_word_ids[start_idx : last_idx + 1])

                            # start a new chunk
                            current_chunk_length = 0

                            if self.word_stride == 0 or non_special_word_ids.index(max(0, current_word_id - self.word_stride)) <= start_idx:
                                # if `word_stride` = 0 or going back `word_stride` would lead to infinite recurssion because it would go
                                # back beyond the start of the last chunk, we don't `word_stride` ... we just move to next token
                                start_idx = last_idx + 1
                            else:
                                current_word_id -= self.word_stride - 1
                                start_idx = non_special_word_ids.index(current_word_id)

                        current_word_id += 1

                        if current_word_id >= max(non_special_word_ids):
                            if current_chunk_length > 0:
                                # add any inprogress chunk
                                chunks.append(non_special_word_ids[start_idx:])
                            break

                    for chunk in chunks:
                        # we already have the example's full list of words and labels, and from them we'll grab the chunks
                        # they are defined in an replicate the pretokenization and label alignment we used before in order to get the same
                        # data *but* just for the chunk
                        chunk_words = [words[word_id] for word_id in list(set(chunk))]
                        chunk_labels = [word_labels[word_id] for word_id in list(set(chunk))]
                        chunked_inputs = hf_tokenizer(chunk_words, truncation=True, **self.tok_kwargs)

                        # grab the inputs "word_ids"
                        chunk_word_ids = chunked_inputs.word_ids() if self.hf_tokenizer.is_fast else self.slow_word_ids_func(self.hf_tokenizer, 0, chunked_inputs)

                        # align labels with tokens
                        chunk_aligned_labels = self.labeling_strategy.align_labels_with_tokens(
                            chunk_word_ids, chunk_labels, self.label_names
                        )

                        row_data = list(chunked_inputs.values()) + [chunk_aligned_labels, chunk_words, chunk_labels]
                        if self.id_attr and self.id_attr in row:
                            row_data.append(row[self.id_attr])
                        if self.is_valid_attr and self.is_valid_attr in row:
                            row_data.append(row[self.is_valid_attr])

                        proc_data.append(row_data)
                else:
                    # if the inputs are <= max_length, no chunking is necessary
                    row_data = list(inputs.values()) + [aligned_labels, words, word_labels]
                    if self.id_attr and self.id_attr in row:
                        row_data.append(row[self.id_attr])
                    if self.is_valid_attr and self.is_valid_attr in row:
                        row_data.append(row[self.is_valid_attr])
                    proc_data.append(row_data)

            # put processed data into a new DataFrame and return
            cols = list(inputs.keys()) + ["aligned_labels", self.text_attrs, self.label_list_attr]
            if self.id_attr and self.id_attr in list(df.columns):
                cols.append(self.id_attr)
            if self.is_valid_attr and self.is_valid_attr in list(df.columns):
                cols.append(self.is_valid_attr)
            final_df = pd.DataFrame(proc_data, columns=cols)

        # return the pre-processed DataFrame
        cols = list(inputs.keys()) + ["aligned_labels", self.text_attrs, self.label_list_attr]
        if self.id_attr and self.id_attr in list(final_df.columns):
            cols.append(self.id_attr)
        if self.is_valid_attr and self.is_valid_attr in list(final_df.columns):
            cols.append(self.is_valid_attr)

        return final_df[cols]

    def process_hf_dataset(self, training_ds: Dataset, validation_ds: Optional[Dataset] = None):
        ds = super().process_hf_dataset(training_ds, validation_ds)

        # return the pre-processed DataFrame
        return ds


# Cell
class HF_TokenTensorCategory(TensorBase):
    pass


# Cell
class HF_TokenCategorize(Transform):
    """Reversible transform of a list of category string to `vocab` id"""

    def __init__(
        self,
        # The unique list of entities (e.g., B-LOC) (default: CategoryMap(vocab))
        vocab: List[str] = None,
        # The token used to identifiy ignored tokens (default: xIGNx)
        ignore_token: str = "[xIGNx]",
        # The token ID that should be ignored when calculating the loss (default: CrossEntropyLossFlat().ignore_index)
        ignore_token_id: int = CrossEntropyLossFlat().ignore_index,
    ):
        self.vocab = None if vocab is None else CategoryMap(vocab, sort=False)
        self.ignore_token, self.ignore_token_id = ignore_token, ignore_token_id

        self.loss_func, self.order = CrossEntropyLossFlat(ignore_index=self.ignore_token_id), 1

    def setups(self, dsets):
        if self.vocab is None and dsets is not None:
            self.vocab = CategoryMap(dsets)
        self.c = len(self.vocab)

    def encodes(self, labels):
        # if `val` is the label name (e.g., B-PER, I-PER, etc...), lookup the corresponding index in the vocab using
        # `self.vocab.o2i`
        ids = [val if (isinstance(val, int)) else self.vocab.o2i[val] for val in labels]
        return HF_TokenTensorCategory(ids)

    def decodes(self, encoded_labels):
        return Category([(self.vocab[lbl_id]) for lbl_id in encoded_labels if lbl_id != self.ignore_token_id])


# Cell
def HF_TokenCategoryBlock(
    # The unique list of entities (e.g., B-LOC) (default: CategoryMap(vocab))
    vocab: Optional[List[str]] = None,
    # The token used to identifiy ignored tokens (default: xIGNx)
    ignore_token: str = "[xIGNx]",
    # The token ID that should be ignored when calculating the loss (default: CrossEntropyLossFlat().ignore_index)
    ignore_token_id: int = CrossEntropyLossFlat().ignore_index,
):
    """`TransformBlock` for per-token categorical targets"""
    return TransformBlock(type_tfms=HF_TokenCategorize(vocab=vocab, ignore_token=ignore_token, ignore_token_id=ignore_token_id))


# Cell
class HF_TokenClassInput(HF_BaseInput):
    pass


# Cell
class HF_TokenClassBeforeBatchTransform(HF_BeforeBatchTransform):
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
        # If you are passing in the "input_ids" as your inputs, set `is_pretokenized` = True
        is_pretokenized: bool = False,
        # The token ID that should be ignored when calculating the loss
        ignore_token_id: int = CrossEntropyLossFlat().ignore_index,
        # The labeling strategy you want to apply when associating labels with word tokens
        labeling_strategy_cls: BaseLabelingStrategy = OnlyFirstTokenLabelingStrategy,
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
        is_split_into_words: bool = True,
        # If using a slow tokenizer, users will need to prove a `slow_word_ids_func` that accepts a
        # tokenizzer, example index, and a batch encoding as arguments and in turn returnes the
        # equavlient of fast tokenizer's `word_ids``
        slow_word_ids_func: Optional[Callable] = None,
        # Any other keyword arguments you want included when using your `hf_tokenizer` to tokenize your inputs
        tok_kwargs: dict = {},
        # Keyword arguments to apply to `HF_TokenClassBeforeBatchTransform`
        **kwargs
    ):

        super().__init__(
            hf_arch,
            hf_config,
            hf_tokenizer,
            hf_model,
            is_pretokenized=is_pretokenized,
            ignore_token_id=ignore_token_id,
            max_length=max_length,
            padding=padding,
            truncation=truncation,
            is_split_into_words=is_split_into_words,
            tok_kwargs=tok_kwargs,
            **kwargs
        )

        self.labeling_strategy = labeling_strategy_cls(hf_tokenizer, ignore_token_id=ignore_token_id)
        self.slow_word_ids_func = slow_word_ids_func

    def encodes(self, samples):
        encoded_samples, inputs = super().encodes(samples, return_batch_encoding=True)

        # if there are no targets (e.g., when used for inference)
        if len(encoded_samples[0]) == 1:
            return encoded_samples

        # get the type of our targets (by default will be HF_TokenTensorCategory)
        target_cls = type(encoded_samples[0][1])

        updated_samples = []
        for idx, s in enumerate(encoded_samples):
            if self.is_pretokenized:
                # if the inputs/targets have already been preprocessed, we only need to apply padding to labels assuming
                # we implored a`BatchLabelingStrategy` in our preprocessing as we do in the TokenClassificationPreprocessor.
                batch_length = len(s[0]["input_ids"])
                if self.hf_tokenizer.padding_side == "right":
                    targ_ids = nn.ConstantPad1d((0, batch_length - len(s[1])), self.ignore_token_id)(s[1])
                else:
                    targ_ids = nn.ConstantPad1d((batch_length - len(s[1]), 0), self.ignore_token_id)(s[1])
            else:
                # with batch-time tokenization, we have to align each token with the correct label using the `word_ids` in the
                # batch encoding object we get from calling our *fast* tokenizer
                word_ids = inputs.word_ids(idx) if self.hf_tokenizer.is_fast else self.slow_word_ids_func(self.hf_tokenizer, idx, inputs)
                targ_ids = target_cls(self.labeling_strategy.align_labels_with_tokens(word_ids, s[1].tolist(), None))

            updated_samples.append((s[0], targ_ids))

        return updated_samples


# Cell
@typedispatch
def show_batch(
    # This typedispatched `show_batch` will be called for `HF_TokenClassInput` typed inputs
    x: HF_TokenClassInput,
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
    # grab our tokenizer
    tfm = first_blurr_tfm(dataloaders, before_batch_tfm_class=HF_TokenClassBeforeBatchTransform)
    hf_arch, hf_tokenizer = tfm.hf_arch, tfm.hf_tokenizer
    vocab = dataloaders.vocab

    res = L()
    for inp, trg, sample in zip(x, y, samples):
        # align "tokens" with labels
        tok_labels = get_token_labels_from_input_ids(hf_tokenizer, inp, trg, vocab)
        # align "words" with labels
        word_labels = get_word_labels_from_token_labels(hf_arch, hf_tokenizer, tok_labels)
        # stringify list of (word,label) for example
        res.append([f"{[ word_targ for idx, word_targ in enumerate(word_labels) if (trunc_at is None or idx < trunc_at) ]}"])

    display_df(pd.DataFrame(res, columns=["word / target label"])[:max_n])
    return ctxs
