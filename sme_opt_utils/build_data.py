from dgl import DGLGraph
import pandas as pd
from rdkit.Chem import MolFromSmiles
import numpy as np
from dgl.data.graph_serialize import save_graphs, load_graphs, load_labels
import torch as th
from rdkit.Chem import BRICS
import random
import os
from rdkit import Chem
from rdkit.Chem import RDConfig
from rdkit.Chem import FragmentCatalog
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem import rdRGroupDecomposition as rdRGD
import itertools
import re
import dgl


# read FunctionGroup information
# with open(fName) as f:
#     file = f.read()

def return_fg_without_c_i_wash(fg_with_c_i, fg_without_c_i):
    # the fragment genereated from smarts would have a redundant carbon, here to remove the redundant carbon
    fg_without_c_i_wash = []
    for fg_with_c in fg_with_c_i:
        for fg_without_c in fg_without_c_i:
            if set(fg_without_c).issubset(set(fg_with_c)):
                fg_without_c_i_wash.append(list(fg_without_c))
    return fg_without_c_i_wash


def return_fg_hit_atom(smiles, fg_name_list, fg_with_ca_list, fg_without_ca_list):
    mol = Chem.MolFromSmiles(smiles)
    hit_at = []
    hit_fg_name = []
    all_hit_fg_at = []
    for i in range(len(fg_with_ca_list)):
        fg_with_c_i = mol.GetSubstructMatches(fg_with_ca_list[i])
        fg_without_c_i = mol.GetSubstructMatches(fg_without_ca_list[i])
        fg_without_c_i_wash = return_fg_without_c_i_wash(fg_with_c_i, fg_without_c_i)
        if len(fg_without_c_i_wash) > 0:
            hit_at.append(fg_without_c_i_wash)
            hit_fg_name.append(fg_name_list[i])
            all_hit_fg_at += fg_without_c_i_wash
    # sort function group atom by atom number
    sorted_all_hit_fg_at = sorted(all_hit_fg_at,
                                  key=lambda fg: len(fg),
                                  reverse=True)
    # remove small function group (wrongly matched), they are part of other big function groups
    remain_fg_list = []
    for fg in sorted_all_hit_fg_at:
        if fg not in remain_fg_list:
            if len(remain_fg_list) == 0:
                remain_fg_list.append(fg)
            else:
                i = 0
                for remain_fg in remain_fg_list:
                    if set(fg).issubset(set(remain_fg)):
                        break
                    else:
                        i += 1
                if i == len(remain_fg_list):
                    remain_fg_list.append(fg)
    # wash the hit function group atom by using the remained fg, remove the small wrongly matched fg
    hit_at_wash = []
    hit_fg_name_wash = []
    for j in range(len(hit_at)):
        hit_at_wash_j = []
        for fg in hit_at[j]:
            if fg in remain_fg_list:
                hit_at_wash_j.append(fg)
        if len(hit_at_wash_j) > 0:
            hit_at_wash.append(hit_at_wash_j)
            hit_fg_name_wash.append(hit_fg_name[j])
    return hit_at_wash, hit_fg_name_wash


def getAllBricsBondSubset(BricsBond):
    all_brics_bond_subset = []
    N = len(BricsBond)
    for i in range(2 ** N):
        brics_bond_subset = []
        for j in range(N):
            if (i >> j) % 2:
                brics_bond_subset.append(BricsBond[j])
        if len(brics_bond_subset) > 0:
            all_brics_bond_subset.append(brics_bond_subset)
        if len(all_brics_bond_subset) > 10000:
            break
    return all_brics_bond_subset


def return_brics_structure_all_substructure(smiles):
    m = Chem.MolFromSmiles(smiles)
    res = list(BRICS.FindBRICSBonds(m))  # [((1, 2), ('1', '5'))]

    # return brics_bond
    all_brics_bond = [set(res[i][0]) for i in range(len(res))]
    all_brics_bond_subset = getAllBricsBondSubset(all_brics_bond)

    all_brics_substructure_subset = dict()
    for i, brics_bond_subset in enumerate(all_brics_bond_subset):
        # return atom in brics_bond_subset
        all_brics_atom = []
        for brics_bond in brics_bond_subset:
            all_brics_atom = list(set(all_brics_atom + list(brics_bond)))

        # return all break atom (the break atoms did'n appear in the same substructure)
        all_break_atom = dict()
        for brics_atom in all_brics_atom:
            brics_break_atom = []
            for brics_bond in brics_bond_subset:
                if brics_atom in brics_bond:
                    brics_break_atom += list(set(brics_bond))
            brics_break_atom = [x for x in brics_break_atom if x != brics_atom]
            all_break_atom[brics_atom] = brics_break_atom

        substrate_idx = dict()
        used_atom = []
        for initial_atom_idx, break_atoms_idx in all_break_atom.items():
            if initial_atom_idx not in used_atom:
                neighbor_idx = [initial_atom_idx]
                substrate_idx_i = neighbor_idx
                begin_atom_idx_list = [initial_atom_idx]
                while len(neighbor_idx) != 0:
                    for idx in begin_atom_idx_list:
                        initial_atom = m.GetAtomWithIdx(idx)
                        neighbor_idx = neighbor_idx + [neighbor_atom.GetIdx() for neighbor_atom in
                                                       initial_atom.GetNeighbors()]
                        exlude_idx = all_break_atom[initial_atom_idx] + substrate_idx_i
                        if idx in all_break_atom.keys():
                            exlude_idx = all_break_atom[initial_atom_idx] + substrate_idx_i + all_break_atom[idx]
                        neighbor_idx = [x for x in neighbor_idx if x not in exlude_idx]
                        substrate_idx_i += neighbor_idx
                        begin_atom_idx_list += neighbor_idx
                    begin_atom_idx_list = [x for x in begin_atom_idx_list if x not in substrate_idx_i]
                substrate_idx[initial_atom_idx] = substrate_idx_i
                used_atom += substrate_idx_i
            else:
                pass
        all_brics_substructure_subset['substructure_subset_{}'.format(i + 1)] = substrate_idx
        all_brics_substructure_subset['substructure_subset_{}_bond'.format(i + 1)] = brics_bond_subset
    substrate_idx = dict()
    substrate_idx[0] = [x for x in range(m.GetNumAtoms())]
    all_brics_substructure_subset['substructure_subset_{}'.format(0)] = substrate_idx
    all_brics_substructure_subset['substructure_subset_{}_bond'.format(0)] = []
    return all_brics_substructure_subset


def return_brics_res_structure(smiles):
    m = Chem.MolFromSmiles(smiles)
    res = list(BRICS.FindBRICSBonds(m))  # [((1, 2), ('1', '5'))]

    # return brics_bond
    all_brics_bond = [set(res[i][0]) for i in range(len(res))]

    all_brics_substructure_subset = dict()
    # return atom in all_brics_bond
    all_brics_atom = []
    for brics_bond in all_brics_bond:
        all_brics_atom = list(set(all_brics_atom + list(brics_bond)))

    if len(all_brics_atom) > 0:
        # return all break atom (the break atoms did'n appear in the same substructure)
        all_break_atom = dict()
        for brics_atom in all_brics_atom:
            brics_break_atom = []
            for brics_bond in all_brics_bond:
                if brics_atom in brics_bond:
                    brics_break_atom += list(set(brics_bond))
            brics_break_atom = [x for x in brics_break_atom if x != brics_atom]
            all_break_atom[brics_atom] = brics_break_atom

        substrate_idx = dict()
        used_atom = []
        for initial_atom_idx, break_atoms_idx in all_break_atom.items():
            if initial_atom_idx not in used_atom:
                neighbor_idx = [initial_atom_idx]
                substrate_idx_i = neighbor_idx
                begin_atom_idx_list = [initial_atom_idx]
                while len(neighbor_idx) != 0:
                    for idx in begin_atom_idx_list:
                        initial_atom = m.GetAtomWithIdx(idx)
                        neighbor_idx = neighbor_idx + [neighbor_atom.GetIdx() for neighbor_atom in
                                                       initial_atom.GetNeighbors()]
                        exlude_idx = all_break_atom[initial_atom_idx] + substrate_idx_i
                        if idx in all_break_atom.keys():
                            exlude_idx = all_break_atom[initial_atom_idx] + substrate_idx_i + all_break_atom[idx]
                        neighbor_idx = [x for x in neighbor_idx if x not in exlude_idx]
                        substrate_idx_i += neighbor_idx
                        begin_atom_idx_list += neighbor_idx
                    begin_atom_idx_list = [x for x in begin_atom_idx_list if x not in substrate_idx_i]
                substrate_idx[initial_atom_idx] = substrate_idx_i
                used_atom += substrate_idx_i
            else:
                pass
    else:
        substrate_idx = dict()
        substrate_idx[0] = [x for x in range(m.GetNumAtoms())]
    all_brics_substructure_subset['substructure'] = substrate_idx
    all_brics_substructure_subset['substructure_bond'] = all_brics_bond

    # add brics res smiles
    brics_leaf_structure_sorted_id = sorted(range(len(all_brics_substructure_subset['substructure'].keys())),
                                            key=lambda k: list(all_brics_substructure_subset['substructure'].keys())[k],
                                            reverse=False)
    m2 = BRICS.BreakBRICSBonds(m)
    frags = Chem.GetMolFrags(m2, asMols=True)
    frags_smi = [Chem.MolToSmiles(x, True) for x in frags]
    sorted_frags_smi = [i for _, i in sorted(zip(list(brics_leaf_structure_sorted_id), frags_smi), reverse=False)]
    sorted_frags_smi = [re.sub(r'\[\d*\*\]', '*', smi) for smi in sorted_frags_smi]
    all_brics_substructure_subset['brics_res_smi'] = sorted_frags_smi
    return all_brics_substructure_subset


def reindex_substructure(substructure_dir):
    # get all atoms in substructure-substructure(ss) bond
    all_atom_list = []
    for bond in substructure_dir['substructure_bond']:
        all_atom_list += list(bond)
    all_atom_list = list(set(all_atom_list))

    # reindex substructure
    substructure_reindex = dict()
    sub_structure = substructure_dir['substructure']
    for i, sub in enumerate(sub_structure.items()):
        substructure_reindex[i] = sub[1]
    substructure_dir['substructure_reindex'] = substructure_reindex

    # get substructure-bond atom'reindex substructure dir
    new_sub_bond_dir = dict()
    for atom in all_atom_list:
        for j, reindex_sub in substructure_reindex.items():
            if atom in reindex_sub:
                new_sub_bond_dir[atom] = j
                break

    # change the substructure_bond to reindex ss-bond
    ss_bond = []
    for bond in substructure_dir['substructure_bond']:
        list_bond = list(bond)
        ss_bond.append([new_sub_bond_dir[list_bond[0]], new_sub_bond_dir[list_bond[1]]])
    substructure_dir['ss_bond'] = ss_bond
    return substructure_dir


def one_of_k_encoding(x, allowable_set):
    if x not in allowable_set:
        raise Exception("input {0} not in allowable set{1}:".format(
            x, allowable_set))
    return [x == s for s in allowable_set]


def one_of_k_encoding_unk(x, allowable_set):
    """Maps inputs not in the allowable set to the last element."""
    if x not in allowable_set:
        x = allowable_set[-1]
    return [x == s for s in allowable_set]


def atom_features(atom, use_chirality=True):
    results = one_of_k_encoding_unk(
        atom.GetSymbol(),
        [
            'B',
            'C',
            'N',
            'O',
            'F',
            'Si',
            'P',
            'S',
            'Cl',
            'As',
            'Se',
            'Br',
            'Te',
            'I',
            'At',
            'other'
        ]) + one_of_k_encoding(atom.GetDegree(),
                               [0, 1, 2, 3, 4, 5, 6]) + \
              [atom.GetFormalCharge(), atom.GetNumRadicalElectrons()] + \
              one_of_k_encoding_unk(atom.GetHybridization(), [
                  Chem.rdchem.HybridizationType.SP, Chem.rdchem.HybridizationType.SP2,
                  Chem.rdchem.HybridizationType.SP3, Chem.rdchem.HybridizationType.SP3D,
                  Chem.rdchem.HybridizationType.SP3D2, 'other']) + [atom.GetIsAromatic()]
    results = results + one_of_k_encoding_unk(atom.GetTotalNumHs(), [0, 1, 2, 3, 4])
    if use_chirality:
        try:
            results = results + one_of_k_encoding_unk(
                atom.GetProp('_CIPCode'),
                ['R', 'S']) + [atom.HasProp('_ChiralityPossible')]
        except:
            results = results + [False, False
                                 ] + [atom.HasProp('_ChiralityPossible')]

    return np.array(results)


def one_of_k_atompair_encoding(x, allowable_set):
    for atompair in allowable_set:
        if x in atompair:
            x = atompair
            break
        else:
            if atompair == allowable_set[-1]:
                x = allowable_set[-1]
            else:
                continue
    return [x == s for s in allowable_set]


def bond_features(bond, use_chirality=True):
    bt = bond.GetBondType()
    bond_feats = [
        bt == Chem.rdchem.BondType.SINGLE, bt == Chem.rdchem.BondType.DOUBLE,
        bt == Chem.rdchem.BondType.TRIPLE, bt == Chem.rdchem.BondType.AROMATIC,
        bond.GetIsConjugated(),
        bond.IsInRing()
    ]
    if use_chirality:
        bond_feats = bond_feats + one_of_k_encoding_unk(
            str(bond.GetStereo()),
            ["STEREONONE", "STEREOANY", "STEREOZ", "STEREOE"])

    return np.array(bond_feats).astype(float)


def etype_features(bond, use_chirality=True):
    bt = bond.GetBondType()
    bond_feats_1 = [
        bt == Chem.rdchem.BondType.SINGLE, bt == Chem.rdchem.BondType.DOUBLE,
        bt == Chem.rdchem.BondType.TRIPLE, bt == Chem.rdchem.BondType.AROMATIC,
    ]
    for i, m in enumerate(bond_feats_1):
        if m == True:
            a = i

    bond_feats_2 = bond.GetIsConjugated()
    if bond_feats_2 == True:
        b = 1
    else:
        b = 0

    bond_feats_3 = bond.IsInRing
    if bond_feats_3 == True:
        c = 1
    else:
        c = 0

    index = a * 1 + b * 4 + c * 8
    if use_chirality:
        bond_feats_4 = one_of_k_encoding_unk(
            str(bond.GetStereo()),
            ["STEREONONE", "STEREOANY", "STEREOZ", "STEREOE"])
        for i, m in enumerate(bond_feats_4):
            if m == True:
                d = i
        index = index + d * 16
    return index


def substructure_features(m, substructure):
    features_list = []
    for i in substructure:
        features_list.append(atom_features(m.GetAtomWithIdx(i)))
    features_np = np.array(features_list)
    features = np.sum(features_np, axis=0)
    return features


# 化学键 分为单键 双键 三键 方向键，转化为整数
BT_MAPPING_INT = {
    Chem.rdchem.BondType.SINGLE: 1,
    Chem.rdchem.BondType.DOUBLE: 2,
    Chem.rdchem.BondType.TRIPLE: 3,
    Chem.rdchem.BondType.AROMATIC: 1.5,
}


def generate_substructure_features(mol, substruct):
    """
    Generates a vector with mapping for a substructure
    :param substruct: The given substructure
    :param mol: RDKit molecule
    :param structure_type: The type of a structure (one of STRUCT_TO_NUM)
    :return: An encoding vector
    """
    atoms = [mol.GetAtomWithIdx(i) for i in substruct]
    substruct_atomic_encoding = np.array([one_of_k_encoding_unk(atom.GetSymbol(),
                                                                [
                                                                    'B',
                                                                    'C',
                                                                    'N',
                                                                    'O',
                                                                    'F',
                                                                    'Si',
                                                                    'P',
                                                                    'S',
                                                                    'Cl',
                                                                    'As',
                                                                    'Se',
                                                                    'Br',
                                                                    'Te',
                                                                    'I',
                                                                    'At',
                                                                    'other'
                                                                ]) for atom in atoms])
    substruct_atomic_sum = np.sum(substruct_atomic_encoding, axis=0).tolist()
    substruct_atomic_sum_norm = [0.1 * atomic_sum for atomic_sum in substruct_atomic_sum]

    # implicit_substruct_valence 计算子结构共价键的数量，单键为1，双键为2，三键为3，方向键为1.5，如：苯环即为9，注意，这里计算的是子结构内部的化合价
    implicit_substruct_valence = 0
    for i in range(len(atoms)):
        for j in range(i, len(atoms)):
            bond = mol.GetBondBetweenAtoms(substruct[i], substruct[j])
            if bond:
                implicit_substruct_valence += BT_MAPPING_INT[
                    mol.GetBondBetweenAtoms(substruct[i], substruct[j]).GetBondType()]

    # 子结构的形式电荷总和
    substruct_formal_charge = sum(atom.GetFormalCharge() for atom in atoms)

    # 子结构的H总和
    substruct_num_Hs = sum(atom.GetTotalNumHs() for atom in atoms)

    # substruct_valence 子结构化合价，这里指的是子结构与其他子结构连接时表现出来的化合价
    substruct_valence = sum(atom.GetExplicitValence() for atom in atoms) - 2 * implicit_substruct_valence

    # 子结构包不包含芳香性
    substruct_is_aromatic = 1 if sum(atom.GetIsAromatic() for atom in atoms) > 0 else 0

    # 子结构原子质量之和
    substruct_mass = sum(atom.GetMass() for atom in atoms)

    # 子结构内部的键之和
    substruct_edges_sum = implicit_substruct_valence

    # 特征加和
    features = substruct_atomic_sum_norm + [substruct_num_Hs * 0.1, substruct_valence, substruct_formal_charge,
                                            substruct_is_aromatic, substruct_mass * 0.01, substruct_edges_sum * 0.1]
    return features


def construct_RGCN_mol_graph_from_smiles(smiles, smask):
    g = DGLGraph()
    # Add nodes
    mol = MolFromSmiles(smiles)
    num_atoms = mol.GetNumAtoms()
    g.add_nodes(num_atoms)
    atoms_feature_all = []
    smask_list = []
    for i, atom in enumerate(mol.GetAtoms()):
        atom_feature = atom_features(atom)
        atoms_feature_all.append(atom_feature)
        if i in smask:
            smask_list.append(0)
        else:
            smask_list.append(1)
    g.ndata["node"] = th.tensor(np.array(atoms_feature_all))
    g.ndata["smask"] = th.tensor(np.array(smask_list)).float()

    # Add edges
    src_list = []
    dst_list = []
    etype_feature_all = []
    num_bonds = mol.GetNumBonds()
    for i in range(num_bonds):
        bond = mol.GetBondWithIdx(i)
        etype_feature = etype_features(bond)
        u = bond.GetBeginAtomIdx()
        v = bond.GetEndAtomIdx()
        src_list.extend([u, v])
        dst_list.extend([v, u])
        etype_feature_all.append(etype_feature)
        etype_feature_all.append(etype_feature)

    g.add_edges(src_list, dst_list)
    g.edata["edge"] = th.tensor(np.array(etype_feature_all))
    return g


def find_murcko_link_bond(mol):
    core = MurckoScaffold.GetScaffoldForMol(mol)
    scaffold_index = mol.GetSubstructMatch(core)
    link_bond_list = []
    num_bonds = mol.GetNumBonds()
    for i in range(num_bonds):
        bond = mol.GetBondWithIdx(i)
        u = bond.GetBeginAtomIdx()
        v = bond.GetEndAtomIdx()
        link_score = 0
        if u in scaffold_index:
            link_score += 1
        if v in scaffold_index:
            link_score += 1
        if link_score == 1:
            link_bond_list.append([u, v])
    return link_bond_list, core


def murcko_res_tokenize_smiles(smiles_str):
    tokens = smiles_str.split('.')
    tokens = [re.sub(r'\[\d*\*\]', '*', token) for token in tokens]
    return tokens


def return_murcko_res_structure(smiles):
    m = Chem.MolFromSmiles(smiles)
    # return murcko_link_bond
    all_murcko_bond, core = find_murcko_link_bond(m)
    res, unmatched = rdRGD.RGroupDecompose([core], [m], asSmiles=True)

    murcko_res = Chem.ReplaceCore(m, core)

    try:
        res_smiles = Chem.MolToSmiles(murcko_res)
        res_list = murcko_res_tokenize_smiles(res_smiles)
        murcko_core_smi = re.sub(r'\[\*\:\d+\]', '*', res[0]['Core'])
        murcko_smi_list = [re.sub(r'\[\*\:\d\]', '*', murcko_core_smi)] + res_list
    except:
        murcko_smi_list = [smiles]

    all_murcko_substructure_subset = dict()
    # return atom in all_murcko_bond
    all_murcko_atom = []
    for murcko_bond in all_murcko_bond:
        all_murcko_atom = list(set(all_murcko_atom + murcko_bond))

    if len(all_murcko_atom) > 0:
        # return all break atom (the break atoms did'n appear in the same substructure)
        all_break_atom = dict()
        for murcko_atom in all_murcko_atom:
            murcko_break_atom = []
            for murcko_bond in all_murcko_bond:
                if murcko_atom in murcko_bond:
                    murcko_break_atom += list(set(murcko_bond))
            murcko_break_atom = [x for x in murcko_break_atom if x != murcko_atom]
            all_break_atom[murcko_atom] = murcko_break_atom

        substrate_idx = dict()
        used_atom = []
        for initial_atom_idx, break_atoms_idx in all_break_atom.items():
            if initial_atom_idx not in used_atom:
                neighbor_idx = [initial_atom_idx]
                substrate_idx_i = neighbor_idx
                begin_atom_idx_list = [initial_atom_idx]
                while len(neighbor_idx) != 0:
                    for idx in begin_atom_idx_list:
                        initial_atom = m.GetAtomWithIdx(idx)
                        neighbor_idx = neighbor_idx + [neighbor_atom.GetIdx() for neighbor_atom in
                                                       initial_atom.GetNeighbors()]
                        exlude_idx = all_break_atom[initial_atom_idx] + substrate_idx_i
                        if idx in all_break_atom.keys():
                            exlude_idx = all_break_atom[initial_atom_idx] + substrate_idx_i + all_break_atom[idx]
                        neighbor_idx = [x for x in neighbor_idx if x not in exlude_idx]
                        substrate_idx_i += neighbor_idx
                        begin_atom_idx_list += neighbor_idx
                    begin_atom_idx_list = [x for x in begin_atom_idx_list if x not in substrate_idx_i]
                substrate_idx[initial_atom_idx] = substrate_idx_i
                used_atom += substrate_idx_i
            else:
                pass
    else:
        substrate_idx = dict()
        substrate_idx[0] = [x for x in range(m.GetNumAtoms())]
    all_murcko_substructure_subset['substructure'] = substrate_idx
    all_murcko_substructure_subset['substructure_bond'] = all_murcko_bond

    # 根据子结构匹配值，对sub_smi重新进行排序
    order_murcko_smi_list = []
    sub_idx_list = [set(value) for value in substrate_idx.values()]
    for sub_idx in sub_idx_list:
        for murcko_smi in murcko_smi_list:
            # 先删除smi中的*号
            murcko_smi_wt_s = murcko_smi.replace("(*)", "")
            murcko_smi_wt_s = murcko_smi_wt_s.replace("*", "")
            murcko_sub = Chem.MolFromSmiles(murcko_smi_wt_s)
            hit_ats = m.GetSubstructMatches(murcko_sub)
            if len(hit_ats)==0:
                murcko_sub = Chem.MolFromSmarts(murcko_smi_wt_s)
                hit_ats = m.GetSubstructMatches(murcko_sub)
            hit_ats = [set(x) for x in hit_ats]
            if sub_idx in hit_ats:
                order_murcko_smi_list.append(murcko_smi)
                break
    all_murcko_substructure_subset['murcko_res_smi'] = order_murcko_smi_list
    # 将子结构与原分子匹配，确定子结构对应的SMILES
    return all_murcko_substructure_subset


def build_mol_graph_data(dataset_smiles, labels_name, smiles_name):
    # 39 function group config
    fName = os.path.join(RDConfig.RDDataDir, 'FunctionalGroups.txt')
    fparams = FragmentCatalog.FragCatParams(1, 6, fName)
    fg_without_ca_smart = ['[N;D2]-[C;D3](=O)-[C;D1;H3]', 'C(=O)[O;D1]', 'C(=O)[O;D2]-[C;D1;H3]',
                           'C(=O)-[H]', 'C(=O)-[N;D1]', 'C(=O)-[C;D1;H3]', '[N;D2]=[C;D2]=[O;D1]',
                           '[N;D2]=[C;D2]=[S;D1]', '[N;D3](=[O;D1])[O;D1]', '[N;R0]=[O;D1]', '[N;R0]-[O;D1]',
                           '[N;R0]-[C;D1;H3]', '[N;R0]=[C;D1;H2]', '[N;D2]=[N;D2]-[C;D1;H3]', '[N;D2]=[N;D1]',
                           '[N;D2]#[N;D1]', '[C;D2]#[N;D1]', '[S;D4](=[O;D1])(=[O;D1])-[N;D1]',
                           '[N;D2]-[S;D4](=[O;D1])(=[O;D1])-[C;D1;H3]', '[S;D4](=O)(=O)-[O;D1]',
                           '[S;D4](=O)(=O)-[O;D2]-[C;D1;H3]', '[S;D4](=O)(=O)-[C;D1;H3]', '[S;D4](=O)(=O)-[Cl]',
                           '[S;D3](=O)-[C;D1]', '[S;D2]-[C;D1;H3]', '[S;D1]', '[S;D1]', '[#9,#17,#35,#53]',
                           '[C;D4]([C;D1])([C;D1])-[C;D1]',
                           '[C;D4](F)(F)F', '[C;D2]#[C;D1;H]', '[C;D3]1-[C;D2]-[C;D2]1', '[O;D2]-[C;D2]-[C;D1;H3]',
                           '[O;D2]-[C;D1;H3]', '[O;D1]', '[O;D1]', '[N;D1]', '[N;D1]', '[N;D1]']
    fg_without_ca_list = [Chem.MolFromSmarts(smarts) for smarts in fg_without_ca_smart]
    fg_with_ca_list = [fparams.GetFuncGroup(i) for i in range(39)]
    fg_smi_list = ['*NC(=O)C', '*C(=O)O', '*C(=O)OC', '*C(=O)', '*C(=O)N', '*C(=O)C', '*N=C=O', '*N=C=S', '*N(O)O', '*N=O', '*=NO', '*=NC'
                , '*N=C', '*N=NC', '*N=N', '*N#N', '*C#N', '*S(=O)(=O)N', '*NS(=O)(=O)C', '*S(=O)(=O)O', '*S(=O)(=O)OC', '*S(=O)(=O)C', '*S(=O)(=O)Cl', '*S(=O)C', '*SC', '*S', '*=S',
                '*[X]', '*C(C)(C)C', '*C(F)(F)F', '*C#C', '*C1CC1', '*OCC', '*OC', '*O', '*=O', '*N', '*=N', '*#N'
                ]

    dataset_mol_gnn = []
    dataset_brics_gnn = []
    dataset_murcko_gnn = []
    dataset_fg_gnn = []
    labels = dataset_smiles[labels_name]
    split_index = dataset_smiles['group']
    smilesList = dataset_smiles[smiles_name]
    mol_n = len(smilesList)
    for i, smiles in enumerate(smilesList):
        # mol graph
        g_rgcn_mol = construct_RGCN_mol_graph_from_smiles(smiles, smask=[])
        mol = [smiles, g_rgcn_mol, labels.loc[i], split_index.loc[i]]
        dataset_mol_gnn.append(mol)
        try:
            # brics mol graph
            brics_substructure_dir = return_brics_res_structure(smiles)
            brics_substructure_mask = []
            for _, substructure in brics_substructure_dir['substructure'].items():
                brics_substructure_mask.append(substructure)
            smask = brics_substructure_mask
            brics_res_smi = brics_substructure_dir['brics_res_smi']
            for j, smask_i in enumerate(smask):
                g_rgcn_brics = construct_RGCN_mol_graph_from_smiles(smiles, smask=smask_i)
                mol_brics = [smiles, g_rgcn_brics, labels.loc[i], split_index.loc[i], smask_i, brics_res_smi[j]]
                dataset_brics_gnn.append(mol_brics)
                print('{}/{}, {}/{} molecule is transformed to BRICS mol graph!'.format(j + 1, len(smask), i + 1,
                                                                                        mol_n))
        except:
            print('{} is transformed failed to brics!'.format(smiles))


        try:
            # murcko graph
            murcko_substructure_dir = return_murcko_res_structure(smiles)
            murcko_substructure_mask = []
            for _, substructure in murcko_substructure_dir['substructure'].items():
                murcko_substructure_mask.append(substructure)
            smask = murcko_substructure_mask
            murcko_res_smi = murcko_substructure_dir['murcko_res_smi']
            for j, smask_i in enumerate(smask):
                g_rgcn_murcko = construct_RGCN_mol_graph_from_smiles(smiles, smask=smask_i)
                mol_murcko = [smiles, g_rgcn_murcko, labels.loc[i], split_index.loc[i], smask_i, murcko_res_smi[j]]
                dataset_murcko_gnn.append(mol_murcko)
                print('{}/{}, {}/{} molecule is transformed to murcko mol graph!'.format(j + 1,
                                                                                         len(smask),
                                                                                         i + 1,
                                                                                         mol_n))
        except:
            print('{} is transformed failed to Murcko!'.format(smiles))

        try:
            # fg graph
            fg_mask = []
            fg_smi = []
            hit_fg_at, hit_fg_smi = return_fg_hit_atom(smiles, fg_smi_list, fg_with_ca_list, fg_without_ca_list)
            for a, hit_fg in enumerate(hit_fg_at):
                for b, hit_fg_b in enumerate(hit_fg):
                    fg_mask.append(hit_fg_b)
                    fg_smi.append(hit_fg_smi[a])
            for j, fg_mask_j in enumerate(fg_mask):
                g_rgcn_fg = construct_RGCN_mol_graph_from_smiles(smiles, smask=fg_mask_j)
                mol_fg = [smiles, g_rgcn_fg, labels.loc[i], split_index.loc[i], fg_mask_j, fg_smi[j]]
                dataset_fg_gnn.append(mol_fg)
                print('{}/{}, {}/{} molecule is transformed to FG mol graph!'.format(j + 1,
                                                                                     len(fg_mask),
                                                                                     i + 1,
                                                                                     mol_n))
        except:
            print('{} is transformed failed to fg!'.format(smiles))
    return dataset_mol_gnn, dataset_brics_gnn, dataset_murcko_gnn, dataset_fg_gnn


def build_mol_graph_for_one_mol(smiles, for_mol=False):
    # 39 function group config
    fName = os.path.join(RDConfig.RDDataDir, 'FunctionalGroups.txt')
    fparams = FragmentCatalog.FragCatParams(1, 6, fName)
    fg_without_ca_smart = ['[N;D2]-[C;D3](=O)-[C;D1;H3]', 'C(=O)[O;D1]', 'C(=O)[O;D2]-[C;D1;H3]',
                           'C(=O)-[H]', 'C(=O)-[N;D1]', 'C(=O)-[C;D1;H3]', '[N;D2]=[C;D2]=[O;D1]',
                           '[N;D2]=[C;D2]=[S;D1]', '[N;D3](=[O;D1])[O;D1]', '[N;R0]=[O;D1]', '[N;R0]-[O;D1]',
                           '[N;R0]-[C;D1;H3]', '[N;R0]=[C;D1;H2]', '[N;D2]=[N;D2]-[C;D1;H3]', '[N;D2]=[N;D1]',
                           '[N;D2]#[N;D1]', '[C;D2]#[N;D1]', '[S;D4](=[O;D1])(=[O;D1])-[N;D1]',
                           '[N;D2]-[S;D4](=[O;D1])(=[O;D1])-[C;D1;H3]', '[S;D4](=O)(=O)-[O;D1]',
                           '[S;D4](=O)(=O)-[O;D2]-[C;D1;H3]', '[S;D4](=O)(=O)-[C;D1;H3]', '[S;D4](=O)(=O)-[Cl]',
                           '[S;D3](=O)-[C;D1]', '[S;D2]-[C;D1;H3]', '[S;D1]', '[S;D1]', '[#9,#17,#35,#53]',
                           '[C;D4]([C;D1])([C;D1])-[C;D1]',
                           '[C;D4](F)(F)F', '[C;D2]#[C;D1;H]', '[C;D3]1-[C;D2]-[C;D2]1', '[O;D2]-[C;D2]-[C;D1;H3]',
                           '[O;D2]-[C;D1;H3]', '[O;D1]', '[O;D1]', '[N;D1]', '[N;D1]', '[N;D1]']
    fg_without_ca_list = [Chem.MolFromSmarts(smarts) for smarts in fg_without_ca_smart]
    fg_with_ca_list = [fparams.GetFuncGroup(i) for i in range(39)]
    fg_smi_list = ['*NC(=O)C', '*C(=O)O', '*C(=O)OC', '*C(=O)', '*C(=O)N', '*C(=O)C', '*N=C=O', '*N=C=S', '*N(O)O', '*N=O', '*=NO', '*=NC'
                , '*N=C', '*N=NC', '*N=N', '*N#N', '*C#N', '*S(=O)(=O)N', '*NS(=O)(=O)C', '*S(=O)(=O)O', '*S(=O)(=O)OC', '*S(=O)(=O)C', '*S(=O)(=O)Cl', '*S(=O)C', '*SC', '*S', '*=S',
                '*[X]', '*C(C)(C)C', '*C(F)(F)F', '*C#C', '*C1CC1', '*OCC', '*OC', '*O', '*=O', '*N', '*=N', '*#N'
                ]

    mol_g_list = []
    smi_sub_list = []
    smask_idx_list = []
    mol_number = Chem.MolFromSmiles(smiles).GetNumAtoms()
    # mol graph
    g_rgcn_mol = construct_RGCN_mol_graph_from_smiles(smiles, smask=[])
    mol_g_list.append(g_rgcn_mol)
    smi_sub_list.append(smiles)
    smask_idx_list.append([])
    if for_mol==True:
        mol_bg = dgl.batch(mol_g_list)
        return mol_bg, smi_sub_list, smask_idx_list
    else:
        try:
            # brics mol graph
            brics_substructure_dir = return_brics_res_structure(smiles)
            brics_substructure_mask = []
            for _, substructure in brics_substructure_dir['substructure'].items():
                brics_substructure_mask.append(substructure)
            smask = brics_substructure_mask
            brics_res_smi = brics_substructure_dir['brics_res_smi']
            for j, smask_i in enumerate(smask):
                if len(smask_i)!=mol_number:
                    g_rgcn_brics = construct_RGCN_mol_graph_from_smiles(smiles, smask=smask_i)
                    mol_g_list.append(g_rgcn_brics)
                    smi_sub_list.append(brics_res_smi[j])
                    smask_idx_list.append(smask[j])
        except:
            pass

        try:
            # murcko graph
            murcko_substructure_dir = return_murcko_res_structure(smiles)
            murcko_substructure_mask = []
            for _, substructure in murcko_substructure_dir['substructure'].items():
                murcko_substructure_mask.append(substructure)
            smask = murcko_substructure_mask
            murcko_res_smi = murcko_substructure_dir['murcko_res_smi']

            # don't use the core and the whole mol, when mol opt
            m = Chem.MolFromSmiles(smiles)
            all_murcko_bond, core = find_murcko_link_bond(m)
            res, unmatched = rdRGD.RGroupDecompose([core], [m], asSmiles=True)
            core_smi = re.sub(r'\[\:\d+\]','*', res[0]['Core'])
            core_smi = re.sub(r'\[\*\:\d\]', '*', core_smi)
            for j, smask_i in enumerate(smask):
                if len(smask_i)!=mol_number:
                    if murcko_res_smi[j]!=core_smi:
                        g_rgcn_murcko = construct_RGCN_mol_graph_from_smiles(smiles, smask=smask_i)
                        mol_g_list.append(g_rgcn_murcko)
                        smi_sub_list.append(murcko_res_smi[j])
                        smask_idx_list.append(smask_i)
        except:
            pass

        try:
            # fg graph
            fg_mask = []
            fg_smi = []
            hit_fg_at, hit_fg_smi = return_fg_hit_atom(smiles, fg_smi_list, fg_with_ca_list, fg_without_ca_list)
            for a, hit_fg in enumerate(hit_fg_at):
                for b, hit_fg_b in enumerate(hit_fg):
                    fg_mask.append(hit_fg_b)
                    fg_smi.append(hit_fg_smi[a])

            for j, fg_mask_j in enumerate(fg_mask):
                if len(fg_mask_j)!=mol_number:
                    g_rgcn_fg = construct_RGCN_mol_graph_from_smiles(smiles, smask=fg_mask_j)
                    mol_g_list.append(g_rgcn_fg)
                    smi_sub_list.append(fg_smi[j])
                    smask_idx_list.append(fg_mask_j)
        except:
            pass
        mol_bg = dgl.batch(mol_g_list)
        return mol_bg, smi_sub_list, smask_idx_list


def build_mol_graph_for_mols(smis):
    # mol graph
    mol_g_list = [construct_RGCN_mol_graph_from_smiles(smi, smask=[]) for smi in smis]
    smask_idx_list = [[] for smi in smis]
    mol_bg = dgl.batch(mol_g_list)
    return mol_bg, smask_idx_list


def built_mol_graph_data_and_save(
        origin_data_path='practice.csv',
        labels_name='label',
        save_g_path='No_name_mol_graph.bin',
        save_g_group_path='No_name_mol_graph_group.csv',
        save_g_for_brics_path='No_name_mol_graph_for_brics.bin',
        save_g_smask_for_brics_path='No_name_mol_graph_smask_for_brics.npy',
        save_g_group_for_brics_path='No_name_mol_graph_group_for_brics.csv',
        save_g_for_murcko_path='No_name_mol_graph_for_murcko.bin',
        save_g_smask_for_murcko_path='No_name_mol_graph_smask_for_murcko.npy',
        save_g_group_for_murcko_path='No_name_mol_graph_group_for_murcko.csv',
        save_g_for_fg_path='No_name_mol_graph_for_fg.bin',
        save_g_smask_for_fg_path='No_name_mol_graph_smask_for_fg.npy',
        save_g_group_for_fg_path='No_name_mol_graph_group_for_fg.csv'

):
    # Ensuring all the output directories exist
    for out_path in [
        save_g_group_path, save_g_path, 
        save_g_group_for_brics_path, save_g_for_brics_path,
        save_g_group_for_murcko_path, save_g_for_murcko_path, 
        save_g_group_for_fg_path, save_g_for_fg_path
    ]:
        dir_name = os.path.dirname(out_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

    data_origin = pd.read_csv(origin_data_path, index_col=None)
    smiles_name = 'smiles'

    dataset_gnn, dataset_gnn_for_brics, dataset_gnn_for_murcko, dataset_gnn_for_fg = build_mol_graph_data(dataset_smiles=data_origin, labels_name=labels_name,
                                        smiles_name=smiles_name)

    smiles, g_rgcn, labels, split_index = map(list, zip(*dataset_gnn))
    graph_labels = {'labels': th.tensor(labels)
                    }
    split_index_pd = pd.DataFrame(columns=['smiles', 'group'])
    split_index_pd.smiles = smiles
    split_index_pd.group = split_index
    split_index_pd.to_csv(save_g_group_path, index=False, columns=None)
    print('Molecules graph is saved!')
    save_graphs(save_g_path, g_rgcn, graph_labels)

    # build data for brics
    smiles, g_rgcn, labels, split_index, smask, brics_res_smi = map(list, zip(*dataset_gnn_for_brics))
    graph_labels = {'labels': th.tensor(labels)
                    }
    split_index_pd = pd.DataFrame(columns=['smiles', 'group', 'sub_smi'])
    split_index_pd.smiles = smiles
    split_index_pd.group = split_index
    split_index_pd.sub_smi = brics_res_smi
    split_index_pd.to_csv(save_g_group_for_brics_path, index=False, columns=None)
    smask_np = np.array(smask, dtype=object)
    np.save(save_g_smask_for_brics_path, smask_np)
    print('Molecules graph for brics is saved!')
    save_graphs(save_g_for_brics_path, g_rgcn, graph_labels)
    #
    # build data for murcko
    smiles, g_rgcn, labels, split_index, smask, murcko_res_smi = map(list, zip(*dataset_gnn_for_murcko))
    graph_labels = {'labels': th.tensor(labels)
                    }
    split_index_pd = pd.DataFrame(columns=['smiles', 'group', 'sub_smi'])
    split_index_pd.smiles = smiles
    split_index_pd.group = split_index
    split_index_pd.sub_smi = murcko_res_smi
    split_index_pd.to_csv(save_g_group_for_murcko_path, index=False, columns=None)
    smask_np = np.array(smask, dtype=object)
    np.save(save_g_smask_for_murcko_path, smask_np)
    print('Molecules graph for murcko is saved!')
    save_graphs(save_g_for_murcko_path, g_rgcn, graph_labels)

    # build data for function group
    smiles, g_rgcn, labels, split_index, fg_mask, fg_smi = map(list, zip(*dataset_gnn_for_fg))
    graph_labels = {'labels': th.tensor(labels)
                    }
    split_index_pd = pd.DataFrame(columns=['smiles', 'group', 'sub_smi'])
    split_index_pd.smiles = smiles
    split_index_pd.group = split_index
    split_index_pd.sub_smi = fg_smi
    split_index_pd.to_csv(save_g_group_for_fg_path, index=False, columns=None)
    fg_mask_np = np.array(fg_mask, dtype=object)
    np.save(save_g_smask_for_fg_path, fg_mask_np)
    print('Molecules graph for function group is saved!')
    save_graphs(save_g_for_fg_path, g_rgcn, graph_labels)


def cal_pair_index(max_index_len):
    all_pair_combination = []
    for i in range(int(max_index_len / 2) + 1):
        if i * 2 != max_index_len:
            all_sub_index = [x for x in range(max_index_len)]
            combination = [sorted(x) for x in itertools.combinations(all_sub_index, i)]
            pair_index_combination = [sorted([sub_index, list(set(all_sub_index).difference(set(sub_index)))]) for
                                      sub_index in combination]
            all_pair_combination = all_pair_combination + pair_index_combination
        else:
            all_sub_index = [x for x in range(max_index_len)]
            combination = [sorted(x) for x in itertools.combinations(all_sub_index, i)]
            pair_index_combination = [sorted([sub_index, list(set(all_sub_index).difference(set(sub_index)))]) for
                                      sub_index in combination]
            pair_index_combination.sort()
            pair_index_combination_norep = [pair_index_combination[i] for i in range(len(pair_index_combination)) if
                                            i % 2 == 0]
            all_pair_combination = all_pair_combination + pair_index_combination_norep
    return all_pair_combination


def emerge_sub(smask, pair_index):
    # 根据子结构的index来合并子结构, 并根据剩余的子结构index合并另一子结构。即将整个分子一分为二。
    emerge_sub_index_1 = []
    emerge_sub_index_2 = []
    for index in pair_index[0]:
        emerge_sub_index_1 = emerge_sub_index_1 + smask[index]
    for index in pair_index[1]:
        emerge_sub_index_2 = emerge_sub_index_2 + smask[index]
    emerge_pair_sub = [emerge_sub_index_1, emerge_sub_index_2]
    return emerge_pair_sub


def load_graph_from_csv_bin_for_splited(
        bin_path='g_atom.bin',
        group_path='g_group.csv',
        smask_path=None,
        random_shuffle=True,
        seed=2022
):
    data = pd.read_csv(group_path)
    smiles = data.smiles.values
    group = data.group.to_list()
    # load substructure name
    if 'sub_smi' in data.columns.tolist():
        sub_smi = data['sub_smi']
    else:
        sub_smi = ['noname' for x in group]

    if random_shuffle:
        random.seed(seed)
        random.shuffle(group)
    homog, detailed_information = load_graphs(bin_path)
    labels = detailed_information['labels']

    # load smask
    if smask_path is None:
        smask = [-1 for x in range(len(group))]
    else:
        smask = np.load(smask_path, allow_pickle=True)

    # calculate not_use index
    train_index = []
    val_index = []
    test_index = []
    for index, group_index in enumerate(group):
        if group_index == 'training':
            train_index.append(index)
        if group_index == 'valid':
            val_index.append(index)
        if group_index == 'test':
            test_index.append(index)
    task_number = 1
    train_set = []
    val_set = []
    test_set = []
    for i in train_index:
        molecule = [smiles[i], homog[i], labels[i], smask[i], sub_smi[i]]
        train_set.append(molecule)

    for i in val_index:
        molecule = [smiles[i], homog[i], labels[i], smask[i], sub_smi[i]]
        val_set.append(molecule)

    for i in test_index:
        molecule = [smiles[i], homog[i], labels[i], smask[i], sub_smi[i]]
        test_set.append(molecule)
    print(len(train_set), len(val_set), len(test_set), task_number)
    return train_set, val_set, test_set, task_number


from torch.utils.data import Dataset
from torch.utils.data import DataLoader


class MolGraphDataset(Dataset):
    def __init__(self, smis):
        self.smis = smis

    def __len__(self):
        return len(self.smis)

    def __getitem__(self, idx):
        smi = self.smis[idx]
        mol_g = construct_RGCN_mol_graph_from_smiles(smi, smask=[])
        return mol_g

def collate_molgraphs(mol_gs):
    # Batch the graphs
    mol_bg = dgl.batch(mol_gs)
    return mol_bg

