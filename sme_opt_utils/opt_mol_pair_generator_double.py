import random
import pandas as pd
from rdkit.Chem import rdmolops
import torch as th
from maskgnn import collate_molgraphs, EarlyStopping, run_a_train_epoch, \
    run_an_eval_epoch, set_random_seed, RGCN, Meter
import pickle as pkl
from build_data import build_mol_graph_for_one_mol
from rdkit import Chem
import itertools
from typing import List


def cal_attri(pred_list):
    mol_pred = pred_list[0]
    sub_pred_list = pred_list[1:]
    attri_sub_list = [mol_pred] + [mol_pred-sub_pred for sub_pred in sub_pred_list]
    return attri_sub_list


def return_atom_num(smi):
    try:
        sub_mol_atom_num = Chem.MolFromSmarts(smi).GetNumAtoms()
        vir_atom_num = str(smi).count("*")
        return sub_mol_atom_num - vir_atom_num
    except:
        return 10000

""""
# fix parameters of model
def SME_opt_sub_detect(smiles, model_name, rgcn_hidden_feats=[64, 64, 64], ffn_hidden_feats=128,
                                  lr=0.0003, classification=False, mode='higher'):
    try:
        args = {}
        args['device'] = "cuda"
        args['node_data_field'] = 'node'
        args['edge_data_field'] = 'edge'
        args['substructure_mask'] = 'smask'
        # model parameter
        args['num_epochs'] = 500
        args['patience'] = 30
        args['batch_size'] = 8
        args['mode'] = 'higher'
        args['in_feats'] = 40
        args['classification'] = classification
        args['rgcn_hidden_feats'] = rgcn_hidden_feats
        args['ffn_hidden_feats'] = ffn_hidden_feats
        args['rgcn_drop_out'] = 0
        args['ffn_drop_out'] = 0
        args['lr'] = lr
        args['loop'] = True
        # task name (model name)
        args['task_name'] = model_name  # change
        rgcn_bg, sub_smi_list, smask_idx_list = build_mol_graph_for_one_mol(smiles)
        sme_opt_detect = pd.DataFrame()
        sme_opt_detect['smiles'] = sub_smi_list
        sme_opt_detect['smask_idx'] = smask_idx_list
        for seed in range(10):
            rgcn_bg_i = rgcn_bg.to(args['device'])
            model = RGCN(ffn_hidden_feats=args['ffn_hidden_feats'],
                         ffn_dropout=args['ffn_drop_out'],
                         rgcn_node_feats=args['in_feats'], rgcn_hidden_feats=args['rgcn_hidden_feats'],
                         rgcn_drop_out=args['rgcn_drop_out'],
                         classification=args['classification'])
            stopper = EarlyStopping(patience=args['patience'], task_name=args['task_name'] + '_' + str(seed + 1),
                                    mode=args['mode'])
            model.to(args['device'])
            stopper.load_checkpoint(model)
            model.eval()
            eval_meter = Meter()
            with th.no_grad():
                rgcn_node_feats = rgcn_bg_i.ndata.pop(args['node_data_field']).float().to(args['device'])
                rgcn_edge_feats = rgcn_bg_i.edata.pop(args['edge_data_field']).long().to(args['device'])
                smask_feats = rgcn_bg_i.ndata.pop(args['substructure_mask']).unsqueeze(dim=1).float().to(args['device'])

                preds, weight = model(rgcn_bg_i, rgcn_node_feats, rgcn_edge_feats, smask_feats)
                eval_meter.update(preds, preds)
                th.cuda.empty_cache()
            y_true, y_pred = eval_meter.compute_metric('return_pred_true')
            if args['classification']:
                y_pred = th.sigmoid(y_pred)
                y_pred = y_pred.squeeze().numpy().tolist()
            else:
                y_pred = y_pred.squeeze().numpy().tolist()
            if type(y_pred).__name__!='list':
                y_pred = [y_pred]
            attri_pred = cal_attri(y_pred)
            sme_opt_detect['attri_{}'.format(seed+1)] = attri_pred
        attri_mean = sme_opt_detect[['attri_{}'.format(i+1) for i in range(10)]].mean(axis=1)
        attri_std = sme_opt_detect[['attri_{}'.format(i+1) for i in range(10)]].std(axis=1)
        sme_opt_detect['attri_mean'] = attri_mean
        sme_opt_detect['attri_std'] = attri_std
        sme_opt_detect_mol = sme_opt_detect[:1]
        pred_value = sme_opt_detect_mol.attri_mean.tolist()[0]
        sme_opt_detect_sub = sme_opt_detect[1:]
        new_sme_opt_detect_sub = sme_opt_detect_sub[
            abs(sme_opt_detect_sub['attri_mean']) > abs(sme_opt_detect_sub['attri_std'])]
        if len(new_sme_opt_detect_sub) > 0:
            sme_opt_detect_sub = new_sme_opt_detect_sub
        sme_opt_detect = pd.concat([sme_opt_detect_mol, sme_opt_detect_sub], axis=0)
        sub_smi_list = sme_opt_detect['smiles'].tolist()
        attri_mean = sme_opt_detect['attri_mean'].tolist()
        #计算每个重原子的平均权重贡献值
        smi_wt_star = [sub_smi.replace("(*)", "") for sub_smi in sub_smi_list]
        smi_wt_star = [sub_smi.replace("*", "") for sub_smi in smi_wt_star]
        smi_he_atom_num = [return_atom_num(smi) for smi in smi_wt_star]
        atom_num = return_atom_num(smiles)
        change_atom_rate = [sub_smi_he_atom_num/atom_num for sub_smi_he_atom_num in smi_he_atom_num]
        sme_opt_detect['change_atom_rate'] = change_atom_rate
        attri_per_he_atom = [attri_mean[i]/smi_atom_num for i, smi_atom_num in enumerate(smi_he_atom_num)]
        connect_num = [sub_smi.count('*') for sub_smi in sub_smi_list]
        sme_opt_detect['attri_per_atom'] = attri_per_he_atom
        sme_opt_detect['sub_atom_num'] = smi_he_atom_num
        sme_opt_detect['connect_num'] = connect_num
        sme_opt_detect = sme_opt_detect[sme_opt_detect['connect_num']<=2]
        sme_opt_detect = sme_opt_detect[sme_opt_detect['change_atom_rate']<=0.35]
        sme_opt_detect.drop_duplicates(subset=['smiles', 'attri_mean'], inplace=True, keep='first')
        sme_opt_detect = sme_opt_detect[sme_opt_detect['smiles']!='NaN']
        sme_opt_detect.to_csv('mol_opt_detect_cache.csv')
        sub_sme_opt_detect = sme_opt_detect
        if mode == 'higher':
            sub_sme_opt_detect.sort_values(by=['attri_per_atom'], ascending=True, inplace=True)
        elif mode == 'lower':
            sub_sme_opt_detect.sort_values(by=['attri_per_atom'], ascending=False, inplace=True)
        sub_smi_to_change = sub_sme_opt_detect.smiles.tolist()[0]
        sub_smi_smask_idx = sub_sme_opt_detect.smask_idx.tolist()[0]
        sub_atom_num = sub_sme_opt_detect.sub_atom_num.tolist()[0]
        sub_smi_to_change_value = sub_sme_opt_detect.attri_per_atom.tolist()[0]
        sub_connect_num = sub_smi_to_change.count("*")
        if sub_connect_num == 0:
            return -1, -1, -1, -1, -1, -1
        else:
            return pred_value, sub_smi_to_change, sub_atom_num, sub_smi_smask_idx, sub_smi_to_change_value, sub_connect_num
    except:
        print('{} mol detect failed.'.format(smiles))
        return -1, -1, -1, -1, -1, -1
    
"""
def SME_opt_sub_detect(smiles, model_name, rgcn_hidden_feats=[64, 64, 64], ffn_hidden_feats=128,
                                  lr=0.0003, classification=False, mode='higher'):
    try:
        print(f"Processing molecule: {smiles}")
        
        # Commenter le cas particulier pour 'OC=O' et le contourner
        # if smiles == 'OC=O':  # Cas particulier pour les molécules simples
        #     print(f"Special case for molecule: {smiles}")
        #     return 0, smiles, 1, [], 0.0, 0

        args = {}
        args['device'] = "cpu"
        args['node_data_field'] = 'node'
        args['edge_data_field'] = 'edge'
        args['substructure_mask'] = 'smask'
        # Model parameters
        args['num_epochs'] = 500
        args['patience'] = 30
        args['batch_size'] = 8
        args['mode'] = 'higher'
        args['in_feats'] = 40
        args['classification'] = classification
        args['rgcn_hidden_feats'] = rgcn_hidden_feats
        args['ffn_hidden_feats'] = ffn_hidden_feats
        args['rgcn_drop_out'] = 0
        args['ffn_drop_out'] = 0
        args['lr'] = lr
        args['loop'] = True
        args['task_name'] = model_name  # Change the task name
        
        #print("Building molecular graph...")
        rgcn_bg, sub_smi_list, smask_idx_list = build_mol_graph_for_one_mol(smiles)
        
        # Vérification de la validité de rgcn_bg et des indices
        if rgcn_bg is None:
            print(f"Error: Failed to build molecular graph for {smiles}")
            return -1, -1, -1, -1, -1, -1
        
        if not smask_idx_list:
            print(f"Error: No substructure mask indices found for {smiles}")
            return -1, -1, -1, -1, -1, -1
        
        #print(f"Substructure mask indices for {smiles}: {smask_idx_list}")

        sme_opt_detect = pd.DataFrame()
        sme_opt_detect['smiles'] = sub_smi_list
        sme_opt_detect['smask_idx'] = smask_idx_list

        for seed in range(10):
            #print(f"Training model with seed {seed + 1}...")
            rgcn_bg_i = rgcn_bg.to(args['device'])
            model = RGCN(ffn_hidden_feats=args['ffn_hidden_feats'],
                         ffn_dropout=args['ffn_drop_out'],
                         rgcn_node_feats=args['in_feats'], rgcn_hidden_feats=args['rgcn_hidden_feats'],
                         rgcn_drop_out=args['rgcn_drop_out'],
                         classification=args['classification'])
            stopper = EarlyStopping(patience=args['patience'], task_name=args['task_name'] + '_' + str(seed + 1),
                                    mode=args['mode'])
            model.to(args['device'])
            stopper.load_checkpoint(model)
            model.eval()
            eval_meter = Meter()
            
            with th.no_grad():
                rgcn_node_feats = rgcn_bg_i.ndata.pop(args['node_data_field']).float().to(args['device'])
                rgcn_edge_feats = rgcn_bg_i.edata.pop(args['edge_data_field']).long().to(args['device'])
                smask_feats = rgcn_bg_i.ndata.pop(args['substructure_mask']).unsqueeze(dim=1).float().to(args['device'])
                #print(f"Model forward pass for seed {seed + 1}...")
                
                preds, weight = model(rgcn_bg_i, rgcn_node_feats, rgcn_edge_feats, smask_feats)
                eval_meter.update(preds, preds)
                th.cuda.empty_cache()
            
            y_true, y_pred = eval_meter.compute_metric('return_pred_true')
            #print(f"Predictions for seed {seed + 1}: {y_pred[:5]}")  # Imprime les 5 premières prédictions
            
            if args['classification']:
                y_pred = th.sigmoid(y_pred)
                y_pred = y_pred.squeeze().numpy().tolist()
            else:
                y_pred = y_pred.squeeze().numpy().tolist()
                
            if type(y_pred).__name__ != 'list':
                y_pred = [y_pred]
                
            attri_pred = cal_attri(y_pred)
            sme_opt_detect['attri_{}'.format(seed + 1)] = attri_pred

        # Calcul des moyennes et écarts-types
        attri_mean = sme_opt_detect[['attri_{}'.format(i + 1) for i in range(10)]].mean(axis=1)
        attri_std = sme_opt_detect[['attri_{}'.format(i + 1) for i in range(10)]].std(axis=1)
        sme_opt_detect['attri_mean'] = attri_mean
        sme_opt_detect['attri_std'] = attri_std

        # Vérification de la forme du DataFrame
        #print(f"Sme_opt_detect DataFrame shape: {sme_opt_detect.shape}")
        
        sme_opt_detect_mol = sme_opt_detect[:1]
        pred_value = sme_opt_detect_mol.attri_mean.tolist()[0]
        sme_opt_detect_sub = sme_opt_detect[1:]

        # Filtrage des sous-structures selon certains critères
        new_sme_opt_detect_sub = sme_opt_detect_sub[
            abs(sme_opt_detect_sub['attri_mean']) > abs(sme_opt_detect_sub['attri_std'])]
        
        if len(new_sme_opt_detect_sub) > 0:
            sme_opt_detect_sub = new_sme_opt_detect_sub
        
        sme_opt_detect = pd.concat([sme_opt_detect_mol, sme_opt_detect_sub], axis=0)
        sub_smi_list = sme_opt_detect['smiles'].tolist()
        attri_mean = sme_opt_detect['attri_mean'].tolist()

        # Calcul des contributions atomiques
        smi_wt_star = [sub_smi.replace("(*)", "") for sub_smi in sub_smi_list]
        smi_wt_star = [sub_smi.replace("*", "") for sub_smi in smi_wt_star]
        
        # Vérification de la validité des SMILES
        #print(f"Processing SMILES: {smi_wt_star[:5]}")  # Affiche les 5 premières molécules après nettoyage

        smi_he_atom_num = [return_atom_num(smi) for smi in smi_wt_star]
        atom_num = return_atom_num(smiles)
        change_atom_rate = [sub_smi_he_atom_num / atom_num for sub_smi_he_atom_num in smi_he_atom_num]
        
        sme_opt_detect['change_atom_rate'] = change_atom_rate
        attri_per_he_atom = [attri_mean[i] / smi_atom_num for i, smi_atom_num in enumerate(smi_he_atom_num)]
        connect_num = [sub_smi.count('*') for sub_smi in sub_smi_list]
        
        sme_opt_detect['attri_per_atom'] = attri_per_he_atom
        sme_opt_detect['sub_atom_num'] = smi_he_atom_num
        sme_opt_detect['connect_num'] = connect_num

        sme_opt_detect = sme_opt_detect[sme_opt_detect['connect_num'] <= 2]
        sme_opt_detect = sme_opt_detect[sme_opt_detect['change_atom_rate'] <= 0.35]
        sme_opt_detect.drop_duplicates(subset=['smiles', 'attri_mean'], inplace=True, keep='first')
        sme_opt_detect = sme_opt_detect[sme_opt_detect['smiles'] != 'NaN']

        sme_opt_detect.to_csv('mol_opt_detect_cache.csv')
        sub_sme_opt_detect = sme_opt_detect
        # Vérification du mode de tri
        if mode == 'higher':
            sub_sme_opt_detect.sort_values(by=['attri_per_atom'], ascending=True, inplace=True)
        elif mode == 'lower':
            sub_sme_opt_detect.sort_values(by=['attri_per_atom'], ascending=False, inplace=True)
        
        sub_smi_to_change = sub_sme_opt_detect.smiles.tolist()[0]
        sub_smi_smask_idx = sub_sme_opt_detect.smask_idx.tolist()[0]
        sub_atom_num = sub_sme_opt_detect.sub_atom_num.tolist()[0]
        sub_smi_to_change_value = sub_sme_opt_detect.attri_per_atom.tolist()[0]
        sub_connect_num = sub_smi_to_change.count("*")

        #print(f"Final selected substructure: {sub_smi_to_change}")
        
        if sub_connect_num == 0:
            print(f"No valid substructure to change for {smiles}")
            return -1, -1, -1, -1, -1, -1
        else:
            return pred_value, sub_smi_to_change, sub_atom_num, sub_smi_smask_idx, sub_smi_to_change_value, sub_connect_num

    except Exception as e:
        print(f'{smiles} mol detect failed: {e}')
        return -1, -1, -1, -1, -1, -1
    


# 返回所有键的index
def get_bond_indices(smiles):
    mol = Chem.MolFromSmiles(smiles)
    bond_indices = []
    for bond in mol.GetBonds():
        bond_indices.append([bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()])
    return bond_indices


# 返回官能团的索引
def get_fg_matches(smiles, fg_smarts):
    """
    识别分子中的官能团并返回其匹配位置

    参数:
    smiles: str, 分子的SMILES表示法
    fg_smarts: str, 要识别的官能团的SMARTS表示法

    返回值:
    matches: list, 由官能团匹配位置组成的列表，每个元素是一个列表，列表中的每个元素是原子的索引
    """

    mol = Chem.MolFromSmiles(smiles)
    fg_mol = Chem.MolFromSmarts(fg_smarts)
    matches = mol.GetSubstructMatches(fg_mol)

    matches_list = []
    for match in matches:
        matches_list.append(list(match))

    return matches_list


def find_broken_atom_idx(bond_list, fg_atom_list):
    result = []
    for lst in bond_list:
        if len(set(lst).intersection(set(fg_atom_list))) == 1:
            num = set(lst).difference(set(fg_atom_list)).pop()
            result.append(num)
    return result


def return_connect_bond_list(connect_atom_1_list, connect_atom_2_list):
    """
    将两个连接原子列表逐一对应，给出所有组合可能性。
    """
    return [list(zip(x, connect_atom_2_list)) for x in itertools.permutations(connect_atom_1_list, len(connect_atom_2_list))]


def get_bond_type(mol, atom1_idx, atom2_idx):
    bond = mol.GetBondBetweenAtoms(atom1_idx, atom2_idx)

    if bond is not None:
        bond_type = bond.GetBondType()
        return bond_type
    else:
        return None


def is_molecule_valid(mol):
    try:
        rdmolops.SanitizeMol(mol)
        return True
    except:
        return False


def generate_optimized_molecules(smiles: str, match: List[int], optimized_fg_smiles: str, re_opt=False) -> List[str]:
    """"smiles 表示化学物质的 SMILES 表示法;
        match 表示需要被替换的官能团原子的索引;
        optimized_fg_smiles 表示需要添加到化学物质中的优化官能团的 SMILES 表示法;
        输出为一个列表，包含优化后的化学物质的 SMILES列表"""

    match.sort(reverse=True)
    mol = Chem.MolFromSmiles(smiles)
    bond_idx_list = get_bond_indices(smiles)
    if not re_opt:
        [atom.SetProp('molAtomMapNumber', '1') for atom in mol.GetAtoms()]
    connect_atom_1 = find_broken_atom_idx(bond_idx_list, match)
    connect_atom_2 = []
    try:
        if len(match) > 0:
            # 创建一个新分子对象
            new_mol = Chem.RWMol(mol)
            # 定义优化官能团的SMILES表示法
            optimized_fg = Chem.MolFromSmiles(optimized_fg_smiles)
            # 添加官能团
            for atom in optimized_fg.GetAtoms():
                atom.SetProp('molAtomMapNumber', '0')
                new_mol.AddAtom(atom)
                if atom.GetSymbol() == '*':
                    connect_atom_2.append(atom.GetIdx())
            for bond in optimized_fg.GetBonds():
                begin_idx = bond.GetBeginAtomIdx() + len(mol.GetAtoms())
                end_idx = bond.GetEndAtomIdx() + len(mol.GetAtoms())
                new_mol.AddBond(begin_idx, end_idx, bond.GetBondType())
            # 得到官能团与原分子连接位置
            connect_bond_list = return_connect_bond_list(connect_atom_1, connect_atom_2)
            # 为官能团与原分子添加连接键
            optimized_molecule_list = []
            for connect_bonds in connect_bond_list:
                new_change_mol = Chem.RWMol(new_mol)
                for bond in connect_bonds:
                    begin_idx = bond[0]
                    end_idx = bond[1] + len(mol.GetAtoms())
                    new_change_mol.AddBond(begin_idx, end_idx, Chem.BondType.SINGLE)
                # 移除原有的官能团
                for atom_idx in match:
                    new_change_mol.RemoveAtom(atom_idx)
                # 先添加连接处的化学键，再删除连接标记
                virtual_connect_atom_list = []
                for atom in new_change_mol.GetAtoms():
                    if atom.GetSymbol() == '*':
                        virtual_connect_atom_list.append(atom.GetIdx())
                        real_bond = sorted([neighbor.GetIdx() for neighbor in atom.GetNeighbors()], reverse=True)
                        # 排序大的为添加的化学键，按照添加的化学键类型来添加化学键
                        bond_type = get_bond_type(new_change_mol, atom.GetIdx(), real_bond[0])
                        new_change_mol.AddBond(real_bond[0], real_bond[1], bond_type)
                # 删除虚拟节点*
                virtual_connect_atom_list.sort(reverse=True)
                for atom_idx in virtual_connect_atom_list:
                    new_change_mol.RemoveAtom(atom_idx)
                if is_molecule_valid(new_change_mol.GetMol()):
                     # 将RWMol对象转换为Mol对象
                    final_mol = new_change_mol.GetMol()
                    optimized_molecule_list.append(Chem.MolToSmiles(final_mol))
                else:
                    print('Smiles:{} match:{} with opt sub:{} is Failed.'.format(smiles, match, optimized_fg_smiles))
    except:
        optimized_molecule_list=[]
    return optimized_molecule_list


def sub_data_filter(sub_data, rm_sub_smi, sub_atom_num, sub_to_change_value, sub_connect_num, mode='higher'):
    data = sub_data[sub_data['sub_connect_num']==sub_connect_num]
    data = data[(data['sub_atom_num']>=sub_atom_num-2)&(data['sub_atom_num']<=sub_atom_num+2)]
    data.sort_values(by=['attri_mean'], ascending=False, inplace=True)
    assert mode in ['higher', 'lower'], \
            'Expect Mode name to be "higher", "lower", got {}'.format(mode)
    if mode =='higher':
        data = data[data['attri_mean'] > sub_to_change_value]
        # data.sort_values(by=['attri_mean'], ascending=False, inplace=True)
    if mode == 'lower':
        data = data[data['attri_mean'] < sub_to_change_value]
        # data.sort_values(by=['attri_mean'], ascending=True, inplace=True)
    data = data[data['sub_smi']!=rm_sub_smi]
    return data['sub_smi'].tolist(), data['attri_mean']


def sme_mol_opt(origin_smi, origin_label, rm_atom_idx, rm_sub_smi, opt_sub_smi, sub_num,  re_opt=False):
    copy_opt_sub_smi = opt_sub_smi
    mol_opt_change_list = []
    opt_smi_list = []
    count = 0
    while (count < sub_num)&(len(opt_sub_smi)!=0):
        try:
            # 随机选择基团
            opt_sub = random.choice(opt_sub_smi)
            opt_sub_smi = [x for x in opt_sub_smi if x != opt_sub]
            optimize_smi_i = random.choice(generate_optimized_molecules(origin_smi, rm_atom_idx, opt_sub, re_opt))
            mol_opt_change_i = '{}->{}'.format(rm_sub_smi, opt_sub)
            mol_opt_change_list.append(mol_opt_change_i)
            opt_smi_list.append(optimize_smi_i)
            count = len(opt_smi_list)
        except:
            pass
    if len(opt_smi_list)<sub_num:
        print(rm_sub_smi, list(set(copy_opt_sub_smi)))
    origin_mol = Chem.MolFromSmiles(origin_smi)
    atoms = [a for a in origin_mol.GetAtoms()]
    [a.SetProp('molAtomMapNumber', '0') for a in atoms if a.GetIdx() in rm_atom_idx]
    [a.SetProp('molAtomMapNumber', '1') for a in atoms if a.GetIdx() not in rm_atom_idx]
    re_origin_smi = Chem.MolToSmiles(origin_mol)
    re_origin_smi_list = [re_origin_smi for x in opt_smi_list]
    origin_label_list = [origin_label for x in opt_smi_list]
    return re_origin_smi_list, origin_label_list, mol_opt_change_list, opt_smi_list


def generate_opt_data(data_name, model_name, sub_name, sample_mol_num, sub_num, mode='higher', random_seed=1216):
    # load hyperparameter
    with open('../result/hyperparameter_{}.pkl'.format(model_name), 'rb') as f:
        hyperparameter = pkl.load(f)
    origin_data = pd.read_csv('../data/origin_data/{}.csv'.format(data_name))
    if hyperparameter['classification']==True:
        if mode == 'lower':
            origin_data = origin_data[origin_data[data_name]==1]
        if mode == 'higher':
            origin_data = origin_data[origin_data[data_name]==0]
    origin_data = origin_data.sample(frac=1, random_state=random_seed)
    origin_smi_list = origin_data['smiles'].tolist()
    origin_label_list = origin_data[data_name].tolist()
    print('origin_data: {}'.format(len(origin_data)))

    opt_data_origin_smi = []
    opt_data_origin_label = []
    opt_data_sub_change = []
    opt_data_opt_mol = []
    n_origin_mol = 0
    sub_data = pd.read_csv('../prediction/summary/{}_{}_sub.csv'.format(sub_name, model_name))
    for i in range(len(origin_data)):
        random_seed = random_seed+1
        if n_origin_mol==sample_mol_num:
            break
        smi = origin_smi_list[i]
        origin_label =origin_label_list[i]

        pred, rm_sub_smi, sub_atom_num, rm_atom_idx, sub_to_change_value, sub_connect_num\
            = SME_opt_sub_detect(smiles=smi, model_name=model_name,
                                 rgcn_hidden_feats=hyperparameter['rgcn_hidden_feats'],
                                 ffn_hidden_feats=hyperparameter['ffn_hidden_feats'],
                                 lr=hyperparameter['lr'], classification=hyperparameter['classification'], mode=mode)
        if rm_sub_smi==-1:
            pass
        else:
            opt_sub_smi, opt_sub_smi_attri = sub_data_filter(sub_data, rm_sub_smi, sub_atom_num, sub_to_change_value, sub_connect_num, mode=mode)
            origin_smi, origin_label, sub_change, optimized_mol_smi = sme_mol_opt(smi, origin_label, rm_atom_idx, rm_sub_smi, opt_sub_smi, sub_num)
            opt_data_origin_smi = opt_data_origin_smi + origin_smi
            opt_data_origin_label = opt_data_origin_label + origin_label
            opt_data_sub_change = opt_data_sub_change + sub_change
            opt_data_opt_mol = opt_data_opt_mol + optimized_mol_smi
            n_origin_mol+=1
            print('{}/{} opt mol is generated, opt mol num: {}.'.format(n_origin_mol, sample_mol_num, len(opt_data_opt_mol)))
    opt_data = pd.DataFrame()
    opt_data['origin_smi'] = opt_data_origin_smi
    opt_data['origin_label'] = opt_data_origin_label
    opt_data['sub_change'] = opt_data_sub_change
    opt_data['opt_smi'] = opt_data_opt_mol
    opt_data.to_csv('../data/generate_data/{}_{}_data.csv'.format(data_name, mode), index=False)


def generate_re_opt_data(data_name, model_name, sub_name, sub_num=1, mode='higher', random_seed=1216):
    # load hyperparameter
    with open('../result/hyperparameter_{}.pkl'.format(model_name), 'rb') as f:
        hyperparameter = pkl.load(f)
    origin_data = pd.read_csv('../data/generate_data/{}_{}_data.csv'.format(data_name, mode))
    first_origin_smi_list = origin_data['origin_smi'].tolist()
    origin_smi_list = origin_data['opt_smi'].tolist()
    origin_label_list = origin_data['origin_label'].tolist()
    print('origin_data: {}'.format(len(origin_data)))

    opt_data_origin_smi = []
    opt_data_origin_label = []
    opt_data_sub_change = []
    opt_data_opt_mol = []
    n_origin_mol = 0
    sub_data = pd.read_csv('../prediction/summary/{}_{}_sub.csv'.format(sub_name, model_name))
    for i in range(len(origin_data)):
        random_seed = random_seed+1
        smi = origin_smi_list[i]
        first_origin_smi = first_origin_smi_list[i]
        origin_label =origin_label_list[i]

        pred, rm_sub_smi, sub_atom_num, rm_atom_idx, sub_to_change_value, sub_connect_num\
            = SME_opt_sub_detect(smiles=smi, model_name=model_name,
                                 rgcn_hidden_feats=hyperparameter['rgcn_hidden_feats'],
                                 ffn_hidden_feats=hyperparameter['ffn_hidden_feats'],
                                 lr=hyperparameter['lr'], classification=hyperparameter['classification'], mode=mode)
        if rm_sub_smi==-1:
            pass
        else:
            opt_sub_smi, opt_sub_smi_attri = sub_data_filter(sub_data, rm_sub_smi, sub_atom_num, sub_to_change_value, sub_connect_num, mode=mode)
            origin_smi, origin_label, sub_change, optimized_mol_smi = sme_mol_opt(smi, origin_label, rm_atom_idx, rm_sub_smi, opt_sub_smi, sub_num, re_opt=True)
            # first origin smi
            opt_data_origin_smi = opt_data_origin_smi + [first_origin_smi for x in range(len(optimized_mol_smi))]
            opt_data_origin_label = opt_data_origin_label + origin_label
            opt_data_sub_change = opt_data_sub_change + sub_change
            opt_data_opt_mol = opt_data_opt_mol + optimized_mol_smi
            n_origin_mol+=1
            print('{}/{} opt mol is generated, opt mol num: {}.'.format(n_origin_mol, len(origin_data), len(opt_data_opt_mol)))
    opt_data = pd.DataFrame()
    opt_data['origin_smi'] = opt_data_origin_smi
    opt_data['origin_label'] = opt_data_origin_label
    opt_data['sub_change'] = opt_data_sub_change
    opt_data['opt_smi'] = opt_data_opt_mol
    opt_data.to_csv('../data/generate_data/re_opt_{}_{}_data.csv'.format(data_name, mode), index=False)


def generate_different_prop_data(data_name, model_name, sub_name, sub_num=1, first_mode='higher', second_mode='lower',  random_seed=1216):
    # load hyperparameter
    with open('../result/hyperparameter_{}.pkl'.format(model_name), 'rb') as f:
        hyperparameter = pkl.load(f)
    origin_data = pd.read_csv('../data/generate_data/{}_{}_data_pred.csv'.format(data_name, first_mode))
    if first_mode=='higher':
        origin_data = origin_data[(origin_data['origin_pred']<0.5)&(origin_data['opt_pred']>=0.5)]
    elif first_mode=='lower':
        origin_data = origin_data[(origin_data['origin_pred']>=0.5)&(origin_data['opt_pred']<0.5)]
    first_origin_smi_list = origin_data['origin_smi'].tolist()
    origin_smi_list = origin_data['opt_smi'].tolist()
    origin_label_list = origin_data['origin_label'].tolist()

    opt_data_origin_smi = []
    opt_data_origin_label = []
    opt_data_sub_change = []
    opt_data_opt_mol = []
    n_origin_mol = 0
    sub_data = pd.read_csv('../prediction/summary/{}_{}_sub.csv'.format(sub_name, model_name))
    for i in range(len(origin_data)):
        random_seed = random_seed+1
        smi = origin_smi_list[i]
        first_origin_smi = first_origin_smi_list[i]
        origin_label =origin_label_list[i]
        if '.' in smi:
            continue
        pred, rm_sub_smi, sub_atom_num, rm_atom_idx, sub_to_change_value, sub_connect_num\
            = SME_opt_sub_detect(smiles=smi, model_name=model_name,
                                 rgcn_hidden_feats=hyperparameter['rgcn_hidden_feats'],
                                 ffn_hidden_feats=hyperparameter['ffn_hidden_feats'],
                                 lr=hyperparameter['lr'], classification=hyperparameter['classification'], mode=second_mode)
        if rm_sub_smi==-1:
            pass
        else:
            opt_sub_smi, opt_sub_smi_attri = sub_data_filter(sub_data, rm_sub_smi, sub_atom_num, sub_to_change_value, sub_connect_num, mode=second_mode)
            origin_smi, origin_label, sub_change, optimized_mol_smi = sme_mol_opt(smi, origin_label, rm_atom_idx, rm_sub_smi, opt_sub_smi, sub_num, re_opt=True)
            # first origin smi
            opt_data_origin_smi = opt_data_origin_smi + [first_origin_smi for x in range(len(optimized_mol_smi))]
            opt_data_origin_label = opt_data_origin_label + origin_label
            opt_data_sub_change = opt_data_sub_change + sub_change
            opt_data_opt_mol = opt_data_opt_mol + optimized_mol_smi
            n_origin_mol+=1
            print('{}/{} opt mol is generated, opt mol num: {}.'.format(n_origin_mol, len(origin_data), len(opt_data_opt_mol)))
    opt_data = pd.DataFrame()
    opt_data['origin_smi'] = opt_data_origin_smi
    opt_data['origin_label'] = opt_data_origin_label
    opt_data['sub_change'] = opt_data_sub_change
    opt_data['opt_smi'] = opt_data_opt_mol
    opt_data.to_csv('../data/generate_data/{}_{}_{}_data.csv'.format(data_name, model_name, first_mode), index=False)


def generate_re_opt_different_prop_data(data_name, model_name, sub_name, sub_num=1, first_mode='higher', second_mode='lower',  random_seed=1216):
    # load hyperparameter
    with open('../result/hyperparameter_{}.pkl'.format(model_name), 'rb') as f:
        hyperparameter = pkl.load(f)
    origin_data = pd.read_csv('../data/generate_data/{}_{}_{}_data.csv'.format(data_name, model_name, first_mode))
    first_origin_smi_list = origin_data['origin_smi'].tolist()
    origin_smi_list = origin_data['opt_smi'].tolist()
    origin_label_list = origin_data['origin_label'].tolist()

    opt_data_origin_smi = []
    opt_data_origin_label = []
    opt_data_sub_change = []
    opt_data_opt_mol = []
    n_origin_mol = 0
    sub_data = pd.read_csv('../prediction/summary/{}_{}_sub.csv'.format(sub_name, model_name))
    for i in range(len(origin_data)):
        random_seed = random_seed+1
        smi = origin_smi_list[i]
        first_origin_smi = first_origin_smi_list[i]
        origin_label =origin_label_list[i]
        if '.' in smi:
            continue
        pred, rm_sub_smi, sub_atom_num, rm_atom_idx, sub_to_change_value, sub_connect_num\
            = SME_opt_sub_detect(smiles=smi, model_name=model_name,
                                 rgcn_hidden_feats=hyperparameter['rgcn_hidden_feats'],
                                 ffn_hidden_feats=hyperparameter['ffn_hidden_feats'],
                                 lr=hyperparameter['lr'], classification=hyperparameter['classification'], mode=second_mode)
        if rm_sub_smi==-1:
            pass
        else:
            opt_sub_smi, opt_sub_smi_attri = sub_data_filter(sub_data, rm_sub_smi, sub_atom_num, sub_to_change_value, sub_connect_num, mode=second_mode)
            origin_smi, origin_label, sub_change, optimized_mol_smi = sme_mol_opt(smi, origin_label, rm_atom_idx, rm_sub_smi, opt_sub_smi, sub_num, re_opt=True)
            # first origin smi
            opt_data_origin_smi = opt_data_origin_smi + [first_origin_smi for x in range(len(optimized_mol_smi))]
            opt_data_origin_label = opt_data_origin_label + origin_label
            opt_data_sub_change = opt_data_sub_change + sub_change
            opt_data_opt_mol = opt_data_opt_mol + optimized_mol_smi
            n_origin_mol+=1
            print('{}/{} opt mol is generated, opt mol num: {}.'.format(n_origin_mol, len(origin_data), len(opt_data_opt_mol)))
    opt_data = pd.DataFrame()
    opt_data['origin_smi'] = opt_data_origin_smi
    opt_data['origin_label'] = opt_data_origin_label
    opt_data['sub_change'] = opt_data_sub_change
    opt_data['opt_smi'] = opt_data_opt_mol
    opt_data.to_csv('../data/generate_data/re_opt_{}_{}_{}_data.csv'.format(data_name, model_name, first_mode), index=False)

if __name__ == '__main__':
    task_name = 'Mutagenicity'

    data_name = task_name
    model_name = 'BBBP'
    sub_name = 'drugbank'
    sub_num = 5


    # low -> high
    print('{} low -> high, {} high -> low'.format(task_name, model_name))
    first_mode = 'higher'

    second_mode = 'lower'
    generate_different_prop_data(data_name, model_name, sub_name, 2, first_mode=first_mode, second_mode=second_mode, random_seed=1216)
    generate_re_opt_different_prop_data(data_name, model_name, sub_name, 2, first_mode=first_mode, second_mode=second_mode, random_seed=2046)

    # high -> low
    print('{} high -> low'.format(task_name))
    first_mode = 'lower'
    second_mode = 'higher'
    generate_different_prop_data(data_name, model_name, sub_name, 2, first_mode=first_mode, second_mode=second_mode, random_seed=1216)
    generate_re_opt_different_prop_data(data_name, model_name, sub_name, 2, first_mode=first_mode, second_mode=second_mode,  random_seed=2046)




















