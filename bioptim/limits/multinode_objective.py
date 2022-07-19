from typing import Callable, Union, Any
from enum import Enum

from ..misc.enums import Node, Reach
from .objective_functions import Objective, ObjectiveFcn
from .penalty_node import PenaltyNodeList
from .multinode_penalty import MultinodePenalty, MultinodePenaltyList, MultinodePenaltyFunctions

# TODO: mirror multinode_constraint.py in here but for objectives
class MultinodeObjective(Objective, MultinodePenalty):
    """
    TODO: docstring
    """

    def __init__(
        self,
        phase_first_idx: int,
        phase_second_idx: int,
        first_node: Union[Node, int],
        second_node: Union[Node, int],
        multinode_objective: Union[Callable, Any] = None,
        custom_function: Callable = None,
        weight: float = 0,
        **params: Any,
    ):
        """
        Parameters
        ----------
        phase_first_idx: int
            The first index of the phase of concern
        params:
            Generic parameters for options
        """
        super(MultinodeObjective, self).__init__(
            multinode_penalty=multinode_objective,
            objective=multinode_objective,
            custom_function=custom_function,
            custom_type=ObjectiveFcn.Mayer,
            reach=Reach.MULTINODE,
            weight=weight,
            **params,
        )
        MultinodePenalty.__init__(
            self,
            phase_first_idx=phase_first_idx,
            phase_second_idx=phase_second_idx,
            first_node=first_node,
            second_node=second_node,
            multinode_penalty=multinode_objective,
            **params,
        )

    def _add_penalty_to_pool(self, all_pn: Union[PenaltyNodeList, list, tuple]):
        ocp = all_pn[0].ocp
        nlp = all_pn[0].nlp

        pool = nlp.J_internal if nlp else ocp.J_internal
        pool[self.list_index] = self

    def clear_penalty(self, ocp, nlp):
        g_to_add_to = nlp.J_internal if nlp else ocp.J_internal

        if self.list_index < 0:
            for i, j in enumerate(g_to_add_to):
                if not j:
                    self.list_index = i
                    return
            else:
                g_to_add_to.append([])
                self.list_index = len(g_to_add_to) - 1
        else:
            while self.list_index >= len(g_to_add_to):
                g_to_add_to.append([])
            g_to_add_to[self.list_index] = []


class MultinodeObjectiveList(MultinodePenaltyList):
    """
    A list of Multi Node Constraint

    Methods
    -------
    add(self, transition: Union[Callable, PhaseTransitionFcn], phase: int = -1, **extra_arguments)
        Add a new MultinodePenalty to the list
    print(self)
        Print the MultinodePenaltyList to the console
    prepare_multinode_penalty(self, ocp) -> list
        Configure all the multinode_objective and put them in a list
    """

    def add(self, multinode_objective: Any, **extra_arguments: Any):
        """
        Add a new MultinodeObjective to the list

        Parameters
        ----------
        multinode_objective: Union[Callable, MultinodePenaltyFcn]
            The chosen phase transition
        extra_arguments: dict
            Any parameters to pass to Penalty
        """

        if not isinstance(multinode_objective, MultinodeObjectiveFcn):  # TODO: might be removed
            extra_arguments["custom_function"] = multinode_objective
            multinode_objective = MultinodeObjectiveFcn.CUSTOM
        super(MultinodeObjectiveList, self)._add(
            option_type=MultinodeObjective, multinode_objective=multinode_objective, phase=-1, **extra_arguments
        )


class MultinodeObjectiveFcn(ObjectiveFcn.Mayer):
    """
    Selection of valid multinode penalty functions
    """

    EQUALITY = MultinodePenaltyFunctions.Functions.equality
    CUSTOM = MultinodePenaltyFunctions.Functions.custom
    COM_EQUALITY = MultinodePenaltyFunctions.Functions.com_equality
    COM_VELOCITY_EQUALITY = MultinodePenaltyFunctions.Functions.com_velocity_equality

    @staticmethod
    def get_type():
        """
        Returns the type of the penalty
        """

        return MultinodePenaltyFunctions
