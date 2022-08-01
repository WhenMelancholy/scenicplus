import pandas as pd
import anndata
import scanpy as sc
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from pygam import LinearGAM,s
from sklearn.preprocessing import MinMaxScaler, StandardScaler
import math
from sklearn.neighbors import NearestNeighbors
from scipy.stats import norm
import matplotlib.cm as cm
from matplotlib.colors import Normalize
import anndata
import ray
from tqdm import tqdm
from scipy.spatial.distance import jensenshannon
from math import ceil, floor
from adjustText import adjust_text
from scenicplus.RSS import _plot_rss_internal
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42

def get_embedding_dpt(adata, group_var, root_group, embedding_key='X_umap', n_dcs=2, figsize=(12,8)):
    adata_h = anndata.AnnData(X=pd.DataFrame(adata.obsm[embedding_key], index=adata.obs.index))
    adata_h.obs = adata.obs.copy()
    sc.pp.neighbors(adata_h)
    adata_h.obs['clusters'] = adata_h.obs[group_var] 
    sc.tl.diffmap(adata_h, random_state=5)
    adata_h.uns['iroot'] = np.flatnonzero(adata_h.obs[group_var]  == root_group)[0]
    sc.tl.dpt(adata_h, n_dcs=n_dcs)
    adata_h.obs['distance'] = adata_h.obs['dpt_pseudotime']
    sc.pl.diffmap(adata_h, color=['clusters', 'distance'], legend_loc='on data', projection='2d')
    adata.obs['dpt_pseudotime'] = adata_h.obs['dpt_pseudotime'].copy()
    adata.obs['distance'] = adata.obs['dpt_pseudotime']
    adata.obs['clusters'] = adata.obs[group_var] 
    sc.pl.embedding(adata, embedding_key, color=['clusters', 'distance'], legend_loc='on data', cmap='viridis')


def get_path_matrix(adata, dpt_var, path_var, path, features, split_groups = True):
    mat_list = []
    if split_groups == True:
        for group in path:
            path_adata = adata.copy()
            path_adata = path_adata[(path_adata.obs[path_var] == group)]
            ordered_cells = path_adata.obs.sort_values(dpt_var).index.tolist()
            path_adata = path_adata[ordered_cells,path_adata.var.index.isin(features)]
            mat = pd.DataFrame(path_adata.X)
            mat.index = path_adata.obs.index
            mat.columns = path_adata.var.index
            mat[dpt_var] = path_adata.obs.loc[:,dpt_var]
            mat_list.append(mat)
        mat = pd.concat(mat_list)
    else:
        path_adata = adata.copy()
        path_adata = path_adata[(path_adata.obs[path_var].isin(path))]
        ordered_cells = path_adata.obs.sort_values(dpt_var).index.tolist()
        path_adata = path_adata[ordered_cells,path_adata.var.index.isin(features)]
        mat = pd.DataFrame(path_adata.X)
        mat.index = path_adata.obs.index
        mat.columns = path_adata.var.index
        mat[dpt_var] = path_adata.obs.loc[:,dpt_var]
    return mat


def fitgam(x,y, feature_range=(0, 1)):
    x = x.reshape(-1,1)
    gam = LinearGAM(s(0)).gridsearch(x, y, progress=False)
    yhat=gam.partial_dependence(term=0, X=x)
    scaler = MinMaxScaler(feature_range=feature_range)
    yhat = scaler.fit_transform(yhat.reshape(-1, 1))
    pval = gam.statistics_['p_values']
    return yhat, pval[0]

def plot_potential(adata, paths_cascades, path, tf, window=1, show_plot=True,
                   return_data=False, gam_smooth=True, dpt_var='distance', use_ranked_dpt=False):    
    gene_data = paths_cascades['Gene'][path]
    region_data = paths_cascades['Region'][path]
    tf_data = paths_cascades['TF'][path]
    
    if use_ranked_dpt:
        dpt = pd.DataFrame(list(range(0,tf_data.shape[0])))
        dpt.index = tf_data.index
        dpt.columns = [dpt_var]
        dpt = dpt.iloc[:,0]
    else:
        dpt = tf_data[dpt_var]
        
    gene_regulon_name = [x for x in gene_data.columns if x.startswith(tf+'_')]
    if len(gene_regulon_name) > 1:
        gene_regulon_name = [x for x in gene_regulon_name if 'extended' not in x]
    region_regulon_name = [x for x in region_data.columns if x.startswith(tf+'_')]
    if len(region_regulon_name) > 1:
        region_regulon_name = [x for x in region_regulon_name if 'extended' not in x]
    
    gene = gene_data[gene_regulon_name[0]]
    region = region_data[region_regulon_name[0]]
    if '_' in tf:
        tf = tf.split('_')[0]
    tf_data = tf_data[tf]
    
    
    
    tf_name = tf.split('_')[0]
    scaler = MinMaxScaler()
    tf_expr_norm = scaler.fit_transform(adata[:,tf_name].X.copy())
    tf_ov = pd.DataFrame(tf_expr_norm, index=adata.obs.index, columns=[tf_name+'_all_paths'])
    tf_ov = tf_ov.loc[tf_data.index]
    tf_ov = tf_ov.iloc[:,0]
    max_value = np.max(tf_ov)
    
    df = pd.DataFrame([tf_data, region, gene, tf_ov, dpt]).T
    df = df.sort_values(dpt_var)
    dpt = np.array(df.iloc[:,4])
    cell_names = df.index
    df = df.rolling(window=window, min_periods=0, axis=0).mean()
    df.index = cell_names
    tf_data = np.array(df.iloc[:,0])
    region = np.array(df.iloc[:,1])
    gene = np.array(df.iloc[:,2])
    tf_ov = np.array(df.iloc[:,3])
    
    if gam_smooth == True:
        tf_data, _ = fitgam(dpt, tf_data, feature_range=(0,1))
        region, _ = fitgam(dpt, region, feature_range=(0,1))
        gene, _ = fitgam(dpt, gene, feature_range=(0,1))
        tf_ov, _ = fitgam(dpt, tf_ov, feature_range=(0,max_value))
    else:
        scaler = MinMaxScaler(feature_range=(0,1))
        tf_data = scaler.fit_transform(tf_data.reshape(-1, 1))
        region = scaler.fit_transform(region.reshape(-1, 1))
        gene = scaler.fit_transform(gene.reshape(-1, 1))
        scaler = MinMaxScaler(feature_range=(0,max_value))
        tf_ov = scaler.fit_transform(tf_ov.reshape(-1, 1))
        
    
    if show_plot == True:
        plt.plot(dpt, tf_data, color='red', label=tf)
        plt.plot(dpt, region, color='green', label=region_regulon_name[0])
        plt.plot(dpt, gene, color='blue', label=gene_regulon_name[0])
        plt.plot(dpt, tf_ov, '--', color='grey', label=tf+'_all_paths')
        plt.title(path)
        plt.legend()
    
    if return_data == True:
        index = df.index
        columns = df.columns
        df = pd.DataFrame([tf_data[:,0], region[:,0], gene[:,0], tf_ov[:,0], dpt]).T
        df.index = index
        df.columns = columns   
        return df
    
def pairwise(iterable):
    from itertools import tee

    a, b = tee(iterable)
    _ = next(b, None)
    yield from zip(a, b)


def get_intersections(a, b):    
    intersections = []
    for x1, y1 in enumerate(a):
        x2 = len(b)
        y2 = y1
        for x3, (y3, y4) in enumerate(pairwise(b)):
            x4 = x3 + 1

            try:
                t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
                u = ((x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)) / ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
            except ZeroDivisionError:
                continue
            if 0 <= t <= 1.0 and 0 <= u <= 1.0:
                px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                #intersections.append((x1, int(px), a.index[x1], b.index[int(px)]))
                intersections.append((a.index[x1], b.index[int(px)], int(px)-x1))
                break
    inter = pd.DataFrame(intersections)
    inter.index = inter.iloc[:,0]
    inter = inter.iloc[:,1:3]
    inter.index.name = None
    inter.columns = ['Match', 'Length']
    return inter

def calculate_arrows(df, penal=0.03):
    tf = df.iloc[:,0]
    rg = df.iloc[:,1]
    g = df.iloc[:,2]
    tf_ov = df.iloc[:,3]

    # TF-to-region
    tf_rg = pd.DataFrame(get_intersections(tf, rg))
    tf_rg.columns = ['tf_to_region_match', 'tf_to_region_length']

    tf_g = pd.DataFrame(get_intersections(tf, g))
    tf_g.columns = ['tf_to_gene_match', 'tf_to_gene_length']

    rg_g = pd.DataFrame(get_intersections(rg, g))
    rg_g.columns = ['region_to_gene_match', 'region_to_gene_length']
    
    arrow_map = pd.concat([df, tf_rg, tf_g, rg_g], axis=1)
    arrow_map['tf_to_region_match'] =  [arrow_map['tf_to_region_match'][i] if not isnan(arrow_map['tf_to_region_match'][i]) else arrow_map.index[i] for i in range(arrow_map.shape[0]) ]
    arrow_map['tf_to_gene_match'] =  [arrow_map['tf_to_gene_match'][i] if not isnan(arrow_map['tf_to_gene_match'][i]) else arrow_map.index[i] for i in range(arrow_map.shape[0]) ]
    arrow_map['region_to_gene_match'] =  [arrow_map['region_to_gene_match'][i] if not isnan(arrow_map['region_to_gene_match'][i]) else arrow_map.index[i] for i in range(arrow_map.shape[0]) ]
    arrow_map = arrow_map.fillna(0) 
    
    # Clean up
    pd.options.mode.chained_assignment = None  
    for i in range(arrow_map.shape[0]):
        if abs(tf[i]-tf_ov[i]) > penal:
            arrow_map['tf_to_region_length'][i] = 0.0
            arrow_map['tf_to_gene_length'][i] = 0.0
            arrow_map['region_to_gene_length'][i] = 0.0
            new_name = arrow_map.index[i]
            arrow_map['tf_to_region_match'][i] = new_name
            arrow_map['tf_to_gene_match'][i] = new_name
            arrow_map['region_to_gene_match'][i] = new_name       
    return arrow_map

def calculate_grid_arrows(embedding, delta_embedding, tf_expr, offset_frac, n_grid_cols, n_grid_rows, n_neighbors, n_cpu):
    #prepare grid
    min_x = min(embedding[:, 0])
    max_x = max(embedding[:, 0])
    min_y = min(embedding[:, 1])
    max_y = max(embedding[:, 1])
    offset_x = (max_x - min_x) * offset_frac
    offset_y = (max_y - min_y) * offset_frac
    #calculate number of points underneath grid points
    x_dist_between_points = (max_x - min_x) / n_grid_cols
    y_dist_between_points = (max_y - min_y) / n_grid_rows
    minimal_distance = np.mean([y_dist_between_points, x_dist_between_points]) #will be used to mask certain points in the grid

    grid_x, grid_y = np.meshgrid(
        np.linspace(min_x + offset_x, max_x - offset_x, n_grid_cols),
        np.linspace(min_y + offset_y, max_y - offset_y, n_grid_rows)
    )
    grid_xy = np.array([np.hstack(grid_x), np.hstack(grid_y)]).T

    #find neighbors of gridpoints
    nn = NearestNeighbors(n_neighbors = n_neighbors, n_jobs = n_cpu)
    nn.fit(embedding)
    dists, neighs = nn.kneighbors(grid_xy)

    std = np.mean([abs(g[1] - g[0]) for g in grid_xy])
    # isotropic gaussian kernel
    gaussian_w = norm.pdf(loc=0, scale=0.5*std, x=dists)
    total_p_mass = gaussian_w.sum(1)

    uv = (delta_embedding[neighs] * gaussian_w[:, :, None]).sum(1) / np.maximum(1, total_p_mass)[:, None]
    tf_expr = tf_expr[neighs].mean(1)
    #norm_c = Normalize()
    #norm_c.autoscale(tf_expr)

    #mask points in the grid which don't have points of the embedding underneath them
    mask = dists.min(1) < minimal_distance

    return grid_xy, uv, mask, tf_expr

def isnan(string):
    return string != string

def plot_map(adata, paths_cascade, tf, color_var, embedding_key = 'X_umap', window=1,
             plot_type='tf_to_gene', gam_smooth = True, use_ranked_dpt = False, tf_traj_thr=0.7, tf_expr_thr=0.2, penalization = 0.03, n_grid_cols = 50,
             n_grid_rows = 50, n_neighbors = 10, offset_frac = 0.1, scale=100, n_cpu = 1,
             figsize =(10, 10), colormap = cm.Greys, plot_streamplot=True, vmax_streamplot=0.25, linewidth_streamplot=0.5, arrowsize_streamplot=2, density_streamplot=10, return_data = False, save=None, **kwargs):
    tf_name = tf.split('_')[0]
    ke = list(paths_cascade[list(paths_cascade.keys())[0]].keys())
    u_list = []
    v_list = []
    x_list = []
    y_list = []
    tf_expr_list = []
    for k in ke:
        df = plot_potential(adata, paths_cascade, k, tf, window=window, return_data=True, show_plot=False, gam_smooth=gam_smooth, use_ranked_dpt = use_ranked_dpt) 
        arrow_map = calculate_arrows(df, penalization)
        embedding = pd.DataFrame(adata.obsm[embedding_key], index=adata.obs.index, columns=['x', 'y'])
        embedding.iloc[:,0] = embedding.iloc[:,0]+abs(min(embedding.iloc[:,0]))
        embedding.iloc[:,1] = embedding.iloc[:,1]+abs(min(embedding.iloc[:,1]))
        embedding = embedding.loc[df.index]
        df = pd.concat([arrow_map, embedding], axis=1)
        df[plot_type+'_match'] =  [df[plot_type+'_match'][i] if not isnan(df[plot_type+'_match'][i]) else df.index[i] for i in range(df.shape[0]) ]
        df[plot_type+'_match'] =  [df[plot_type+'_match'][i] if df.iloc[i,0] > tf_traj_thr else df.index[i] for i in range(df.shape[0]) ]
        df[plot_type+'_match'] =  [df[plot_type+'_match'][i] if df.iloc[i,3] > tf_expr_thr else df.index[i] for i in range(df.shape[0]) ]
        df = df.loc[:,['x', 'y', plot_type+'_match', tf_name+'_all_paths']].dropna()
        x = df.loc[:,'x']
        y = df.loc[:,'y']
        u = np.array(df.loc[df[plot_type+'_match'], 'x'])-np.array(x)
        v = np.array(df.loc[df[plot_type+'_match'], 'y'])-np.array(y)
        tf_expr = np.array(df.iloc[:,3])
        u_list.append(u)
        v_list.append(v)
        x_list.append(x)
        y_list.append(y)
        tf_expr_list.append(tf_expr)
    u = np.concatenate(u_list)
    v = np.concatenate(v_list)
    x = np.concatenate(x_list)
    y = np.concatenate(y_list)
    tf_expr = np.concatenate(tf_expr_list)
    # Plot as grid
    embedding = np.array([x,y]).T
    delta_embedding = np.array([u,v]).T
    grid_xy, uv, mask, color = calculate_grid_arrows(embedding, delta_embedding, tf_expr, offset_frac, n_grid_cols, n_grid_rows, n_neighbors, n_cpu)
    from matplotlib.pyplot import rc_context
    with rc_context({'figure.figsize': figsize}):
        sc.pl.embedding(adata, embedding_key, color=[color_var], zorder=0, return_fig=True, title=tf, **kwargs) 
    if plot_streamplot is True:
        distances = np.sqrt((uv**2).sum(1))
        norm = matplotlib.colors.Normalize(vmin=0, vmax=vmax_streamplot, clip=True)
        mapper = cm.ScalarMappable(norm=norm, cmap=colormap)
        scale = lambda X: [(x - min(X)) / (max(X) - min(X)) for x in X]
        uv[~mask] = np.nan
        plt.streamplot(
                grid_xy.reshape(n_grid_cols,n_grid_cols, 2)[:, :, 0],
                grid_xy.reshape(n_grid_cols,n_grid_cols, 2)[:, :, 1],
                uv.reshape(n_grid_cols,n_grid_cols, 2)[:, :, 0],
                uv.reshape(n_grid_cols,n_grid_cols, 2)[:, :, 1], density = density_streamplot, color = np.array(scale(distances)).reshape(n_grid_cols,n_grid_cols), cmap = colormap, zorder = 1, norm = norm,
                linewidth = linewidth_streamplot, arrowsize=arrowsize_streamplot)
    else:    
        plt.quiver(grid_xy[mask, 0], grid_xy[mask, 1], uv[mask, 0], uv[mask, 1], zorder=1, color=colormap(color[mask]), scale=scale)
    if save is not None:
        plt.savefig(save)
    if return_data == True:
        return df
        
def select_regulons(tf, selected_features):
    gene_regulon_name = [x for x in selected_features['Gene'] if x.startswith(tf+'_')]
    if len(gene_regulon_name) > 1:
        gene_regulon_name = [x for x in gene_regulon_name if 'extended' not in x]
    region_regulon_name = [x for x in selected_features['Region'] if x.startswith(tf+'_')]
    if len(region_regulon_name) > 1:
        region_regulon_name = [x for x in region_regulon_name if 'extended' not in x]
    return [tf.split('_')[0], region_regulon_name[0], gene_regulon_name[0]]
    
def cell_forces(adata, paths_cascade, plot_type='tf_to_gene', window=1, gam_smooth=True, use_ranked_dpt=False,
                tf_traj_thr=0.7, tf_expr_thr=0.2, selected_eGRNs=None, penalization=0.05, n_cpu = 1, **kwargs):
    ke = list(paths_cascade[list(paths_cascade.keys())[0]].keys())
    df_list=[]
    if selected_eGRNs is None:
        selected_eGRNs = paths_cascade['Gene'][ke[0]].columns
    if n_cpu == 1: 
        for tf in selected_eGRNs:
            df = cell_forces_per_tf(adata, paths_cascade, tf, ke, plot_type, window, gam_smooth, use_ranked_dpt,
                tf_traj_thr, tf_expr_thr, selected_eGRNs, penalization)
            if df is not None:
                df_list.append(df)
    else:
        ray.init(num_cpus=n_cpu, **kwargs)
        try:
            jobs = []
            for tf in tqdm(selected_eGRNs, total=len(selected_eGRNs), desc='initializing'):
                jobs.append(cell_forces_per_tf_ray.remote(adata, paths_cascade, tf, ke, plot_type, window, gam_smooth, use_ranked_dpt,
                tf_traj_thr, tf_expr_thr, selected_eGRNs, penalization))
            def to_iterator(obj_ids):
                while obj_ids:
                    finished_ids, obj_ids = ray.wait(obj_ids)
                    for finished_id in finished_ids:
                        yield ray.get(finished_id)
            for df in tqdm(to_iterator(jobs),
                            total=len(jobs),
                            desc=f'Running using {n_cpu} cores',
                            smoothing=0.1):
                if df is not None:
                    df_list.append(df)
        except Exception as e:
            print(e)
        finally:
            ray.shutdown()
            
    if len(df_list) > 0:
        df = pd.concat(df_list, axis=1)
        return df
    else:
        return None

@ray.remote
def cell_forces_per_tf_ray(adata, paths_cascade, tf, ke, plot_type='tf_to_gene', window=1, gam_smooth=True, use_ranked_dpt=False,
                tf_traj_thr=0.7, tf_expr_thr=0.2, selected_eGRNs=None, penalization=0.05):
    return cell_forces_per_tf(adata, paths_cascade, tf, ke, plot_type, window, gam_smooth, use_ranked_dpt,
                tf_traj_thr, tf_expr_thr, selected_eGRNs, penalization)
    
def cell_forces_per_tf(adata, paths_cascade, tf, ke, plot_type='tf_to_gene', window=1, gam_smooth=True, use_ranked_dpt=False,
                tf_traj_thr=0.7, tf_expr_thr=0.2, selected_eGRNs=None, penalization=0.05):
    flag = True
    df_list_TF = []
    for k in ke:
        if paths_cascade['TF'][k][tf.split('_')[0]].sum() > 0:
            df = plot_potential(adata, paths_cascade, k, tf, window=window, return_data=True, show_plot=False, gam_smooth=gam_smooth, use_ranked_dpt=use_ranked_dpt) 
            df = calculate_arrows(df, penalization)
            df[plot_type+'_match'] =  [df[plot_type+'_match'][i] if df.iloc[i,0] > tf_traj_thr and df.iloc[i,3] > tf_expr_thr else df.index[i] for i in range(df.shape[0])]
            df[plot_type+'_length'] =  [df[plot_type+'_length'][i] if df[plot_type+'_match'][i] != df.index[i] else 0.0 for i in range(df.shape[0])]
            df = df.loc[:,[plot_type+'_length']].fillna(0.0)
            df = df.reset_index()
            df_list_TF.append(df)
        else:
            flag = False
    if flag is True:
        df = pd.concat(df_list_TF)
        df = df.sort_values(plot_type+'_length', ascending=False)
        df = df.drop_duplicates(subset='index', keep='first')
        df.index = df.loc[:,'index']
        df = df.loc[:,[plot_type+'_length']]
        df.columns = [tf]
        df.index.name = None
        df = df.loc[adata.obs.index,:]
        return df
    else:
        return None
    
def forces_rss(adata, df,  variable):
    data_mat = df
    cell_data_series = adata.obs.loc[data_mat.index, variable]
    cell_data = list(cell_data_series.unique())
    n_types = len(cell_data)
    regulons = list(data_mat.columns)
    n_regulons = len(regulons)
    rss_values = np.empty(shape=(n_types, n_regulons), dtype=np.float)

    def rss(aucs, labels):
        # jensenshannon function provides distance which is the sqrt of the JS divergence.
        return 1.0 - jensenshannon(aucs / aucs.sum(), labels / labels.sum())

    for cidx, regulon_name in enumerate(regulons):
        for ridx, type in enumerate(cell_data):
            rss_values[ridx, cidx] = rss(
                data_mat[regulon_name], (cell_data_series == type).astype(int))

    rss_values = pd.DataFrame(
        data=rss_values, index=cell_data, columns=regulons)
    return rss_values
    
def plot_forces_rss(rss_values,
             top_n = 5,
             selected_groups = None,
             num_columns = 1,
             figsize = (6.4, 4.8),
             fontsize = 12,
             save = None):
    data_mat = rss_values
    if selected_groups is None:
        cats = sorted(data_mat.index.tolist())
    else:
        cats = selected_groups

    if num_columns > 1:
        num_rows = int(np.ceil(len(cats) / num_columns))
        if figsize == (6.4, 4.8):
            figsize = (6.4 * num_columns, 4.8 * num_rows)
        i = 1
        fig = plt.figure(figsize=figsize)

    pdf = None
    if (save is not None) & (num_columns == 1):
        pdf = matplotlib.backends.backend_pdf.PdfPages(save)

    for c in cats:
        x = data_mat.T[c]
        if num_columns > 1:
            ax = fig.add_subplot(num_rows, num_columns, i)
            i = i + 1
        else:
            fig = plt.figure(figsize=figsize)
            ax = plt.axes()
        _plot_rss_internal(data_mat, c, top_n=top_n, max_n=None, ax=ax)
        ax.set_ylim(x.min()-(x.max()-x.min())*0.05,
                    x.max()+(x.max()-x.min())*0.05)
        for t in ax.texts:
            t.set_fontsize(fontsize)
        ax.set_ylabel('')
        ax.set_xlabel('')
        adjust_text(ax.texts, autoalign='xy', ha='right', va='bottom', arrowprops=dict(
            arrowstyle='-', color='lightgrey'), precision=0.001)
        if num_columns == 1:
            fig.text(0.5, 0.0, 'eRegulon rank', ha='center',
                     va='center', size='x-large')
            fig.text(0.00, 0.5, 'eRegulon specificity score (eRSS)',
                     ha='center', va='center', rotation='vertical', size='x-large')
            plt.tight_layout()
            plt.rcParams.update({
                'figure.autolayout': True,
                'figure.titlesize': 'large',
                'axes.labelsize': 'medium',
                'axes.titlesize': 'large',
                'xtick.labelsize': 'medium',
                'ytick.labelsize': 'medium'
            })
            if save is not None:
                pdf.savefig(fig, bbox_inches='tight')
            plt.show()

    if num_columns > 1:
        fig.text(0.5, 0.0, 'eRegulon rank', ha='center',
                 va='center', size='x-large')
        fig.text(0.00, 0.5, 'eRegulon specificity score (eRSS)',
                 ha='center', va='center', rotation='vertical', size='x-large')
        plt.tight_layout()
        plt.rcParams.update({
            'figure.autolayout': True,
            'figure.titlesize': 'large',
            'axes.labelsize': 'medium',
            'axes.titlesize': 'large',
            'xtick.labelsize': 'medium',
            'ytick.labelsize': 'medium'
        })
        if save is not None:
            fig.savefig(save, bbox_inches='tight')
        plt.show()
    if (save is not None) & (num_columns == 1):
        pdf = pdf.close()