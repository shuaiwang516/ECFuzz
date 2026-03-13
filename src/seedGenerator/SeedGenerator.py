import copy
import csv
import random
from typing import List, Tuple, Dict

from dataModel.ConfItem import ConfItem
from dataModel.Seed import Seed
from utils.ConfAnalyzer import ConfAnalyzer
from utils.Configuration import Configuration
from utils.ExerciseGuidanceState import ExerciseGuidanceState
from utils.Logger import getLogger
from utils.ShowStats import ShowStats


class SeedGenerator(object):
    """
    Seed Generator is responsible for generating high quality seeds according to the information
    offered by `ConfAnalyzer`.


    """

    def __init__(self) -> None:
        self.logger = getLogger()
        self.seedPool: List[Seed] = []
        fuzzerConf = Configuration.fuzzerConf

        self.seedPoolSelectionRatio = float(fuzzerConf['seed_pool_selection_ratio'])

        self.confItemsBasic: List[str] = ConfAnalyzer.confItemsBasic
        self.confItemMutable: List[str] = ConfAnalyzer.confItemsMutable
        self.confItemMutableSize: int = len(self.confItemMutable)
        self.sequentialGeneratorIndex: int = 0
        self.confItems: List[str] = self.confItemsBasic + self.confItemMutable
        self.confItemRelations: Dict[str, List[List[str, str]]] = ConfAnalyzer.confItemRelations
        self.confItemTypeMap: Dict[str, str] = ConfAnalyzer.confItemTypeMap
        self.confItemValueMap: Dict[str, str] = ConfAnalyzer.confItemValueMap
        self.lastGeneratedSeed = None

        self.logger.info("SeedGenerator initialized.")

    def updateConfMutable(self) -> None:
        # update mutable 
        for confName in ConfAnalyzer.excludeConf:
            if confName in self.confItemMutable:
                self.confItemMutable.remove(confName)
        # update size
        self.confItemMutableSize = len(self.confItemMutable)
        # update confItems
        for confName in ConfAnalyzer.excludeConf:
            if confName in self.confItems:
                self.confItems.remove(confName)
        

    def generateSeed(self) -> Seed:
        """
        The generateSeed function generates a new seed.

        If the seed pool is not empty, there is a 50% chance that the last generated seed will be used as the new one.
        Otherwise, k random configuration items are selected from all possible configuration items and related ones
        (i.e., those with an edge in the dependency graph) to form a new Seed object. The value of k is determined by
        randomly choosing an integer between 1 and n where n denotes all possible configuration items in total.

        Args:
            self: Access the attributes and methods of the class in python

        Returns:
            Seed: 
        """
        ShowStats.currentJob = 'generating seed'
        fromPool = self.seedPool.__len__() > 0 and random.random() > self.seedPoolSelectionRatio
        if fromPool:
            self.logger.info("Random Choose a Seed from pool.")
            self.lastGeneratedSeed = random.choice(self.seedPool)
        else:  
            self.logger.info("Try creating a Seed...")
            candidate_names = copy.deepcopy(self.confItemMutable)
            candidate_names, candidate_source = ExerciseGuidanceState.choose_candidate_names(candidate_names)
            self.logger.info(f">>>>[SeedGenerator] candidate source is {candidate_source} with {len(candidate_names)} names")
            # k = random.randint(1, confItemList.__len__())
            if Configuration.fuzzerConf['mutator'].split(".")[-1] == "SingleMutator":
                k = 1
            else:
                k = random.randint(3, 6)
            k = min(k, len(candidate_names)) if candidate_names else 0

            if k == 0:
                candidate_names = copy.deepcopy(self.confItemMutable)
                candidate_source = "baseline-fallback"
                k = 1 if Configuration.fuzzerConf['mutator'].split(".")[-1] == "SingleMutator" else min(3, len(candidate_names))

            if random.random() > float(Configuration.fuzzerConf['seed_gen_seq_ratio']):
                confItemList = copy.deepcopy(candidate_names)
                random.shuffle(confItemList)
                confItemList = confItemList[:k]
            else:
                candidate_count = len(candidate_names)
                if candidate_count == 0:
                    confItemList = []
                else:
                    if self.sequentialGeneratorIndex >= candidate_count:
                        self.sequentialGeneratorIndex = 0
                    b = min(candidate_count, self.sequentialGeneratorIndex + k)
                    confItemList = candidate_names[self.sequentialGeneratorIndex: b]
                    self.sequentialGeneratorIndex = 0 if b >= candidate_count else b

            if len(confItemList) == 0 and len(candidate_names) != 0:
                self.logger.info(">>>>[SeedGenerator] sequential selection produced an empty seed; falling back to random candidate selection")
                confItemList = copy.deepcopy(candidate_names)
                random.shuffle(confItemList)
                fallback_k = min(max(1, k), len(confItemList))
                confItemList = confItemList[:fallback_k]
                    
            relatedConfItems = []
            for confItemName in confItemList:
                if self.confItemRelations.__contains__(confItemName):
                    relatedConfItems.extend(relation[0] for relation in self.confItemRelations[confItemName] if relation[0] in self.confItems)
                    
            if float(Configuration.fuzzerConf['seed_pool_selection_ratio']) == float(1) and float(Configuration.fuzzerConf['seed_gen_seq_ratio']) == 0:
                relatedConfItems = []

            confItemList += relatedConfItems

            confItemList = [ConfItem(name, self.confItemTypeMap[name], self.confItemValueMap[name])
                            for name in confItemList]

            self.lastGeneratedSeed = Seed(confItemList)
            self.lastGeneratedSeed.exerciseWorkloadSignature = ExerciseGuidanceState.workloadSignature
            # self.addSeedToPool(self.lastGeneratedSeed)

        return self.lastGeneratedSeed

    def addSeedToPool(self, seed: Seed) -> None:
        """
        Add a seed that may be interesting to the seed pool.

        Args:
            seed: a possibly interesting seed.

        Returns:
            None
        """
        self.seedPool.append(seed)
        ShowStats.queueLength += 1
