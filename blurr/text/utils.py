# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/01_text-utils.ipynb (unless otherwise specified).

__all__ = ['BlurrText', 'NLP', 'HF_TASKS', 'HF_ARCHITECTURES']

# Cell
import os, importlib, inspect, random, sys, torch
from typing import List, Optional, Union, Tuple, Type

import numpy as np
import pandas as pd

from enum import Enum
from fastcore.foundation import L
from transformers import AutoConfig, AutoTokenizer, PretrainedConfig, PreTrainedTokenizerBase, PreTrainedModel, logging

from ..utils import Singleton

logging.set_verbosity_error()


# Cell
@Singleton
class BlurrText:
    """A general utility class for getting your Hugging Face objects"""

    def __init__(self):
        # get hf classes (tokenizers, configs, models, etc...)
        transformer_classes = inspect.getmembers(importlib.import_module("transformers"))

        # build a df that we can query against to get various transformers objects/info
        self._df = pd.DataFrame(transformer_classes, columns=["class_name", "class_location"])
        self._df = self._df[self._df.class_location.apply(lambda v: isinstance(v, type))]

        # add the module each class is included in
        self._df["module"] = self._df.class_location.apply(lambda v: v.__module__)

        # remove class_location (don't need it anymore)
        self._df.drop(labels=["class_location"], axis=1, inplace=True)

        # break up the module into separate cols
        module_parts_df = self._df.module.str.split(".", n=-1, expand=True)
        for i in range(len(module_parts_df.columns)):
            self._df[f"module_part_{i}"] = module_parts_df[i]

        # using module part 1, break up the functional area and arch into separate cols
        module_part_3_df = self._df.module_part_3.str.split("_", n=1, expand=True)
        self._df[["functional_area", "arch"]] = module_part_3_df

        self._df["arch"] = self._df["arch"].str.replace("_fast", "")

        # transformers >=4.5.x does "auto" differently; so remove it and "utils" from "arch" column
        self._df = self._df[~self._df["arch"].isin(["auto", "utils"])]

        # if functional area = modeling, pull out the task it is built for
        model_type_df = self._df[(self._df.functional_area == "modeling")].class_name.str.rsplit("For", n=1, expand=True)

        model_type_df[1] = np.where(model_type_df[1].notnull(), "For" + model_type_df[1].astype(str), model_type_df[1])

        self._df["model_task"] = model_type_df[1]
        self._df["model_task"] = self._df["model_task"].str.replace("For", "", n=1, case=True, regex=False)

        model_type_df = self._df[(self._df.functional_area == "modeling")].class_name.str.rsplit("With", n=1, expand=True)
        model_type_df[1] = np.where(
            model_type_df[1].notnull(), "With" + model_type_df[1].astype(str), self._df[(self._df.functional_area == "modeling")].model_task
        )

        self._df["model_task"] = model_type_df[1]
        self._df["model_task"] = self._df["model_task"].str.replace("With", "", n=1, case=True, regex=False)

        # look at what we're going to remove (use to verify we're just getting rid of stuff we want too)
        # df[~df['hf_class_type'].isin(['modeling', 'configuration', 'tokenization'])]

        # only need these 3 functional areas for our querying purposes
        self._df = self._df[self._df["functional_area"].isin(["modeling", "configuration", "tokenization"])]

    def get_tasks(self, arch: str = None):
        """This method can be used to get a list of all tasks supported by your transformers install, or
        just those available to a specific architecture
        """
        query = ["model_task.notna()"]
        if arch:
            query.append(f'arch == "{arch}"')

        return sorted(self._df.query(" & ".join(query), engine="python").model_task.unique().tolist())

    def get_architectures(self):
        return sorted(self._df[(self._df.arch.notna()) & (self._df.arch != None)].arch.unique().tolist())

    def get_models(
        self,
        arch: str = None,
        task: str = None
    ):
        """The transformer models available for use (optional: by architecture | task)"""
        query = ['functional_area == "modeling"']
        if arch:
            query.append(f'arch == "{arch}"')
        if task:
            query.append(f'model_task == "{task}"')

        models = sorted(self._df.query(" & ".join(query)).class_name.tolist())
        return models

    def get_model_architecture(self, model_name_or_enum):
        """Get the architecture for a given model name / enum"""
        model_name = model_name_or_enum if isinstance(model_name_or_enum, str) else model_name_or_enum.name
        return self._df[self._df.class_name == model_name].arch.values[0]

    def get_hf_objects(
        self,
        pretrained_model_name_or_path: Optional[Union[str, os.PathLike]],
        model_cls: PreTrainedModel,
        config: Union[PretrainedConfig, str, os.PathLike] = None,
        tokenizer_cls: PreTrainedTokenizerBase = None,
        config_kwargs: dict = {},
        tokenizer_kwargs: dict = {},
        model_kwargs: dict = {},
        cache_dir: Union[str, os.PathLike] = None
    ) -> Tuple[str, PretrainedConfig, PreTrainedTokenizerBase, PreTrainedModel]:
        """
        Given at minimum a `pretrained_model_name_or_path` and `model_cls (such as
        `AutoModelForSequenceClassification"), this method returns all the Hugging Face objects you need to train
        a model using Blurr
        """
        # config
        if config is None:
            config = AutoConfig.from_pretrained(pretrained_model_name_or_path, cache_dir=cache_dir, **config_kwargs)

        # tokenizer (gpt2, roberta, bart (and maybe others) tokenizers require a prefix space)
        if any(s in pretrained_model_name_or_path for s in ["gpt2", "roberta", "bart", "longformer"]):
            tokenizer_kwargs = {**{"add_prefix_space": True}, **tokenizer_kwargs}

        if tokenizer_cls is None:
            tokenizer = AutoTokenizer.from_pretrained(pretrained_model_name_or_path, cache_dir=cache_dir, **tokenizer_kwargs)
        else:
            tokenizer = tokenizer_cls.from_pretrained(pretrained_model_name_or_path, cache_dir=cache_dir, **tokenizer_kwargs)

        # model
        model = model_cls.from_pretrained(pretrained_model_name_or_path, config=config, cache_dir=cache_dir, **model_kwargs)

        # arch
        arch = self.get_model_architecture(type(model).__name__)

        return (arch, config, tokenizer, model)


# Cell
NLP = BlurrText()


# Cell
HF_TASKS = Enum("HF_TASKS_ALL", NLP.get_tasks())


# Cell
HF_ARCHITECTURES = Enum("HF_ARCHITECTURES", NLP.get_architectures())